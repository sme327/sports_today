"""Framework-light Today-page assembly for the Django migration.

The existing adapters and scoring services remain the source of truth. This module
only translates an HTTP query into the same slate and opportunity presentation used
by the Streamlit page.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from datetime import date, timedelta
from html import escape
from time import perf_counter
from urllib.parse import urlencode

from django.core.cache import cache

import leagues  # noqa: F401 - populate adapter registry
from components.game_cards import group_games_by_state, schedule_grid_html
from components.opportunity_feed import opportunity_feed_html
from domain.markets import LABELS, ORDER, prop_type_for
from domain.models import DataStatus, Opportunity, OpportunityMode, SlateGame, SourceStatus
from leagues.base import LeagueAdapter, get_adapter, iter_adapters
from services import grading
from services.calibration import annotate
from services.editorial import best_per_league, league_norms
from services.freshness import get_freshness
from services.schedules import get_slate
from services import daily_feed

ANALYSIS_LEAGUES = {"MLB", "WNBA"}
LEDGER_LIMIT = 100_000
CURATION_MAX = 8


def query_link(**values: str | int | None) -> str:
    return "?" + urlencode({k: v for k, v in values.items() if v is not None})


def parse_day(raw: str | None, today: date) -> tuple[str, date]:
    day = raw if raw in {"today", "tomorrow"} else "today"
    return day, today + timedelta(days=1 if day == "tomorrow" else 0)


def parse_threshold(raw: str | None) -> int:
    try:
        value = int(raw or "90")
    except ValueError:
        return 90
    return value if value in {85, 90, 95} else 90


def prop_type_of(opp: Opportunity) -> str:
    return prop_type_for(opp.market_key, opp.league, opp.market)


def present_prop_types(opps: list[Opportunity]) -> list[str]:
    present = {prop_type_of(opp) for opp in opps}
    return [key for key in ORDER if key in present]


def _cached_slate(adapter: LeagueAdapter, slate_date: date) -> tuple[list[SlateGame], DataStatus]:
    league_key = adapter.league.lower().replace(" ", "-")
    key = f"django:slate:{league_key}:{slate_date.isoformat()}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    result = get_slate(adapter, slate_date)
    cache.set(key, result, timeout=120)
    return result


def load_slates(slate_date: date) -> dict[str, tuple[list[SlateGame], DataStatus]]:
    slates: dict[str, tuple[list[SlateGame], DataStatus]] = {}
    for adapter in iter_adapters():
        try:
            slates[adapter.league] = _cached_slate(adapter, slate_date)
        except Exception as exc:  # one league must never take down the page
            slates[adapter.league] = (
                [],
                DataStatus(adapter.source_name, SourceStatus.ERROR, None, str(exc)),
            )
    return slates


def _logo_map(games: list[SlateGame]) -> dict[str, str]:
    out: dict[str, str] = {}
    for game in games:
        for name, logo in (
            (game.away_name, game.away_logo),
            (game.away_short, game.away_logo),
            (game.away_abbr, game.away_logo),
            (game.home_name, game.home_logo),
            (game.home_short, game.home_logo),
            (game.home_abbr, game.home_logo),
        ):
            if name and logo:
                out[str(name)] = logo
    return out


def _stamp(opps: list[Opportunity], games: list[SlateGame], adapter: LeagueAdapter) -> list[Opportunity]:
    logos = _logo_map(games)
    game_ids: dict[str, str] = {}
    for game in games:
        for identity in (game.away_name, game.away_abbr, game.home_name, game.home_abbr):
            key = adapter.match_team(identity)
            if key:
                game_ids[key] = game.game_id
    stamped = []
    for opp in opps:
        key = adapter.match_team(opp.team_name)
        stamped.append(
            dataclasses.replace(
                opp,
                image_url=opp.image_url or logos.get(str(opp.team_name)),
                game_id=opp.game_id or (game_ids.get(key) if key else None),
            )
        )
    return stamped


def build_opportunities(slate_date: date, visible: dict[str, list[SlateGame]]) -> tuple[list[Opportunity], list[str]]:
    slate_opps: list[Opportunity] = []
    analysis_leagues: list[str] = []
    for league in ANALYSIS_LEAGUES:
        games = visible.get(league) or []
        adapter = get_adapter(league)
        if not games or adapter is None:
            continue
        analysis_leagues.append(league)
        team_ids = sorted({team for game in games for team in game.team_identifiers})
        opps = adapter.opportunities(
            as_of=slate_date,
            scheduled_team_ids=team_ids,
            mode=OpportunityMode.SLATE,
            limit=LEDGER_LIMIT,
        )
        slate_opps.extend(_stamp(opps, games, adapter))

    mlb_games = visible.get("MLB") or []
    mlb = get_adapter("MLB")
    if mlb_games and mlb is not None:
        team_ids = sorted({team for game in mlb_games for team in game.team_identifiers})
        slate_opps.extend(
            _stamp(
                mlb.k_opportunities(
                    as_of=slate_date,
                    scheduled_team_ids=team_ids,
                    limit=LEDGER_LIMIT,
                ),
                mlb_games,
                mlb,
            )
        )
        probables = sorted(
            {
                (str(game.meta.get(key)), display)
                for game in mlb_games
                for key, display in (
                    ("away_pitcher", game.away_display),
                    ("home_pitcher", game.home_display),
                )
                if game.meta.get(key) and str(game.meta.get(key)).upper() != "TBD"
            }
        )
        if probables:
            from services.data_access import load_plate_appearances
            from services.mlb_pitcher_props import build_pitcher_opportunities

            pa = load_plate_appearances(as_of=slate_date)
            pitcher_opps = build_pitcher_opportunities(pa, probables, slate_date)
            slate_opps.extend(_stamp(pitcher_opps, mlb_games, mlb))

    annotate(slate_opps)
    slate_opps.sort(key=lambda opportunity: opportunity.sort_key, reverse=True)
    return slate_opps, analysis_leagues


def _game_counts(opps: list[Opportunity], threshold: int) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for opp in opps:
        if opp.game_id and opp.opportunity_score >= threshold:
            counts[opp.game_id] += 1
    return dict(counts)


def build_context(params, local_today: date) -> dict:
    started = perf_counter()
    day, slate_date = parse_day(params.get("day"), local_today)
    threshold = parse_threshold(params.get("thr"))
    collapsed = params.get("games") == "off"
    focus = params.get("focus")
    chosen_prop = params.get("prop")

    slates = daily_feed.load_cached_schedules(slate_date)
    schedule_read_ms = (perf_counter() - started) * 1000
    adapters = [get_adapter(name) for name, (games, _) in slates.items() if games]
    adapters = [adapter for adapter in adapters if adapter is not None]
    available = {adapter.league for adapter in adapters}
    requested = {value for value in params.getlist("league") if value in available}
    selected = requested or available
    visible = {
        adapter.league: slates[adapter.league][0] if adapter.league in selected else []
        for adapter in adapters
    }
    all_visible = [game for games in visible.values() for game in games]
    slate_opps, feed_calculated_at = daily_feed.load(slate_date)
    visible_leagues = {league for league, games in visible.items() if games}
    slate_opps = [opp for opp in slate_opps if opp.league in visible_leagues]
    analysis_leagues = sorted({opp.league for opp in slate_opps})
    feed_read_ms = (perf_counter() - started) * 1000 - schedule_read_ms
    counts = _game_counts(slate_opps, threshold)

    schedule_groups: list[str] = []
    unjudged: list[str] = []
    if all_visible and not collapsed:
        best_ids, unjudged = best_per_league(all_visible)
        norms = league_norms(all_visible)
        schedule_groups = [
            schedule_grid_html(group, day, counts, threshold, set(best_ids.values()), norms)
            for group in group_games_by_state(all_visible)
            if group
        ]

    game_labels = {
        str(game.game_id): f"{game.away_display} @ {game.home_display}" for game in all_visible
    }
    focused = [opp for opp in slate_opps if not focus or str(opp.game_id) == focus]
    prop_types = present_prop_types(focused)
    if chosen_prop not in prop_types:
        chosen_prop = None
    filtered = [opp for opp in focused if not chosen_prop or prop_type_of(opp) == chosen_prop]
    if focus:
        displayed = filtered
        opportunity_summary = f"{len(displayed)} {'opportunity' if len(displayed) == 1 else 'opportunities'} in this game"
    else:
        displayed = [opp for opp in filtered if opp.opportunity_score >= grading.CURATION_FLOOR][
            :CURATION_MAX
        ]
        opportunity_summary = (
            f"Today’s {len(displayed)} strongest {'pick' if len(displayed) == 1 else 'picks'} · "
            f"curated from {len(filtered):,} scored"
            if displayed
            else ""
        )

    errors = [
        f"{status.source}: {status.detail or 'schedule unavailable'}"
        for league, (games, status) in slates.items()
        if status.status is SourceStatus.ERROR and (league in selected or games)
    ]
    fresh = get_freshness()
    return {
        "day": day,
        "slate_date": slate_date,
        "collapsed": collapsed,
        "threshold": threshold,
        "league_filters": [
            {
                "key": adapter.league,
                "label": adapter.label,
                "active": adapter.league in requested,
            }
            for adapter in adapters
        ],
        "schedule_groups": schedule_groups,
        "game_count": len(all_visible),
        "unjudged": ", ".join(unjudged),
        "errors": errors,
        "has_analysis": bool(analysis_leagues),
        "focus_label": game_labels.get(focus),
        "chosen_prop": chosen_prop,
        "prop_filters": [
            {"key": key, "label": LABELS.get(key, key), "active": key == chosen_prop}
            for key in prop_types
        ],
        "opportunity_summary": opportunity_summary,
        "opportunity_html": opportunity_feed_html(displayed) if displayed else "",
        "has_scored_opportunities": bool(filtered),
        "freshness": fresh,
        "feed_calculated_at": feed_calculated_at,
        "timing": {
            "schedule_ms": round(schedule_read_ms, 1),
            "feed_ms": round(feed_read_ms, 1),
            "total_ms": round((perf_counter() - started) * 1000, 1),
        },
        "query": query_link,
        "current_leagues": sorted(requested),
    }
