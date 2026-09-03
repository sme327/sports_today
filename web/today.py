"""Framework-light Today-page assembly.

The adapters and scoring services remain the source of truth. This module only
translates an HTTP query into the precomputed slate and opportunity presentation
(services/daily_feed.py builds both; nothing here scores or fetches).
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from time import perf_counter
from urllib.parse import quote, unquote_plus, urlencode

import leagues  # noqa: F401 - populate adapter registry
from components.game_cards import group_games_by_state, schedule_grid_html
from components.opportunity_feed import opportunity_feed_html
from domain.markets import LABELS, ORDER, prop_type_for
from domain.models import Opportunity, SourceStatus
from leagues.base import get_adapter
from services import daily_feed, grading
from services.editorial import best_per_league, league_norms
from services.freshness import get_freshness

CURATION_MAX = 8


def query_link(**values: str | int | None) -> str:
    return "?" + urlencode({k: v for k, v in values.items() if v is not None})


_MATCHUP_LINK = re.compile(
    r'href="\?day=([^&"]+)&amp;league=([^&"]+)&amp;game=([^&"]+)"'
    r'|href="\?day=([^&"]+)&league=([^&"]+)&game=([^&"]+)"'
)


def django_matchup_links(html: str) -> str:
    """Translate shared Streamlit query links into Django matchup routes."""
    def replace(match: re.Match) -> str:
        values = match.groups()[:3] if match.group(1) is not None else match.groups()[3:]
        day, league, game_id = (unquote_plus(value) for value in values)
        return (
            f'href="/game/{quote(league, safe="")}/{quote(game_id, safe="")}/'
            f'?day={quote(day, safe="")}"'
        )
    return _MATCHUP_LINK.sub(replace, html)


# The slate days the site precomputes, as offsets from the build date. The third is
# deliberately not linked from anywhere: it is the back pocket the client-side rollover
# promotes into "tomorrow" once the calendar has moved past the build. Adding a day here
# is most of what it takes to hold one more (the other half is _SEEDS in export_static).
DAY_OFFSETS = {"today": 0, "tomorrow": 1, "day-after": 2}

# Days the navigation offers directly. "day-after" is reachable only by rollover, so the
# nav never grows a third pill and the slate keeps its two-way toggle.
NAV_DAYS = ("today", "tomorrow")


def parse_day(raw: str | None, today: date) -> tuple[str, date]:
    day = raw if raw in DAY_OFFSETS else "today"
    return day, today + timedelta(days=DAY_OFFSETS[day])


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
        # Which of today's games the race page would call consequential. Non-fatal:
        # a card without the chip is merely quieter, and standings are context.
        try:
            from services.mlb_playoffs import slate_implications
            race = slate_implications(all_visible, slate_date)
        except Exception:                                    # noqa: BLE001
            race = {}
        schedule_groups = [
            django_matchup_links(
                schedule_grid_html(group, day, counts, threshold,
                                   set(best_ids.values()), norms, race)
            )
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
        # Which of the precomputed days this page is, so the client-side roll-over knows
        # where it stands without having to parse its own URL. The flag gates the script
        # in base.html: matchup pages also carry a slate_date, and they must neither run
        # the roll-over (a game page addresses one game, not "today") nor render
        # `const index = ;` from an absent day_index, which is a syntax error that would
        # take the whole inline script down with it.
        "day_index": DAY_OFFSETS[day],
        "slate_rollover": True,
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
        "opportunity_html": opportunity_feed_html(displayed, game_labels) if displayed else "",
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
