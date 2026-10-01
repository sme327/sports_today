"""Django matchup-page assembly using the existing league page models."""

from __future__ import annotations

from datetime import date
from time import perf_counter

from django.core.cache import cache

from components import mlb_game as mlb_components
from components import mls_game as mls_components
from components import wnba_game as wnba_components
from components.opportunity_feed import opportunity_feed_html
from domain.models import SlateGame
from services.daily_feed import load_cached_schedules
from services.mlb_game_page import ENGINE_VERSION, build_mlb_game_page
from services.mls_game_page import (
    ENGINE_VERSION as MLS_ENGINE_VERSION,
    build_mls_game_page,
)
from services.wnba_game_page import (
    ENGINE_VERSION as WNBA_ENGINE_VERSION,
    build_wnba_game_page,
)
from services import matchup_cache


def find_game(league: str, game_id: str, slate_date: date) -> SlateGame | None:
    slates = load_cached_schedules(slate_date)
    games, _status = slates.get(league.upper(), ([], None))
    return next((game for game in games if str(game.game_id) == str(game_id)), None)


def mlb_context(game: SlateGame, slate_date: date) -> dict:
    started = perf_counter()
    cache_key = f"django:mlb-page:{ENGINE_VERSION}:{slate_date.isoformat()}:{game.game_id}"
    page = cache.get(cache_key)
    cache_source = "memory" if page is not None else None
    if page is None:
        page = matchup_cache.load("MLB", str(game.game_id), slate_date, ENGINE_VERSION)
        if page is not None:
            cache.set(cache_key, page, timeout=900)
            cache_source = "database"
    if page is None:
        page = build_mlb_game_page(game, slate_date, slate_date)
        matchup_cache.store("MLB", str(game.game_id), slate_date, ENGINE_VERSION, page)
        cache.set(cache_key, page, timeout=900)
        cache_source = "built"

    hero, series = _postseason_hero(game, page.hero, slate_date)
    chunks = [
        mlb_components.hero_html(hero, series),
        _prop_desk(game, slate_date),
        mlb_components.team_identity_html(page.away_identity, page.home_identity),
        mlb_components.game_story_html(page.game_story),
        mlb_components.key_matchups_html(page.key_matchups),
        mlb_components.pitcher_trends_html(page.pitcher_trends),
    ]
    batter_trends = mlb_components.batter_trends_html(page.batter_trends)
    chunks.append(
        batter_trends
        or mlb_components.player_trends_html(page.heating_up, page.cooling_off)
    )
    if page.opportunities:
        labels = {str(game.game_id): f"{game.away_display} @ {game.home_display}"}
        opportunities = opportunity_feed_html(list(page.opportunities), labels)
    else:
        opportunities = (
            '<div class="mlb-empty">No game-specific opportunities currently meet '
            "the display threshold.</div>"
        )
    chunks.extend(
        [
            '<div class="mlb-section"><div class="mlb-section-head">'
            "<h2>Players Positioned to Succeed</h2></div>"
            f"{opportunities}</div>",
            mlb_components.game_shape_html(page.game_shape),
            mlb_components.storylines_html(page.storylines),
            mlb_components.data_context_html(page.data_status.detail)
            if page.data_status and page.data_status.detail
            else "",
        ]
    )
    return {
        "section": "today",
        "league": "MLB",
        "game": game,
        "slate_date": slate_date,
        "day": "tomorrow" if slate_date > date.today() else "today",
        "content_chunks": [chunk for chunk in chunks if chunk],
        "cache_source": cache_source,
        "build_ms": round((perf_counter() - started) * 1000, 1),
    }


def _prop_desk(game: SlateGame, slate_date: date) -> str:
    """The postseason prop desk, under the header and above the existing analysis.

    Postseason only for now (decision log 2026-09-30). Built at render time, like the
    series strip: lineups post a few hours before first pitch, and a page cached at the
    morning build would otherwise keep yesterday's order all day. Non-fatal — the rest of
    the page stands on its own.
    """
    if not game.is_postseason:
        return ""
    key = f"django:mlb-prop-desk:v1:{slate_date.isoformat()}:{game.game_id}"
    html = cache.get(key)
    if html is not None:
        return html
    try:
        from components.prop_desk import prop_desk_html
        from services import mlb_analytics, mlb_prop_desk
        from services.data_access import load_plate_appearances
        from services.lineups import get_lineups

        pa = load_plate_appearances(as_of=slate_date)
        meta = game.meta or {}
        desk = mlb_prop_desk.build(
            pa, away_team=game.away_name or "", home_team=game.home_name or "",
            away_short=game.away_short or game.away_display,
            home_short=game.home_short or game.home_display,
            away_pid=mlb_analytics.match_pitcher(pa, meta.get("away_pitcher")),
            home_pid=mlb_analytics.match_pitcher(pa, meta.get("home_pitcher")),
            lineups=get_lineups(slate_date))
        html = prop_desk_html(desk)
    except Exception:                                    # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("prop desk failed for %s", game.game_id)
        html = ""
    cache.set(key, html, timeout=300)
    return html


def _postseason_hero(game: SlateGame, hero, slate_date: date):
    """Reframe the hero for a postseason game: seeds and the series, not games back.

    "3rd in AL East, 11 GB" is true of a Wild Card club and beside the point — in October
    the reader wants the round, the seeds and who leads the series. Applied here, at
    render time, rather than in the cached page model: the series moves every night and
    the model is cached per slate day, so baking it in would serve yesterday's standing.

    Falls back to the slate game's own series fields (the source's wording) when no
    bracket was collected, so a postseason game is never framed as a regular-season one.
    """
    from dataclasses import replace

    if not game.is_postseason:
        return hero, None
    try:
        from services import mlb_bracket
        info = mlb_bracket.game_in_series(mlb_bracket.load(slate_date), game.game_id)
    except Exception:                                    # noqa: BLE001
        info = None

    def _line(standing: str | None, seed: int | None) -> str | None:
        record = (standing or "").split(" · ")[0]
        bits = [f"No. {seed} seed" if seed else None,
                f"{record} in the regular season" if record else None]
        return " · ".join(b for b in bits if b) or None

    # The form pill describes the regular season (playoff games are excluded from season
    # reads), so on a playoff page it says so — "heating up" must not read as "including
    # Game 1".
    hero = replace(
        hero,
        away_form_note=f"Regular-season form: {hero.away_form_note[0].lower()}{hero.away_form_note[1:]}"
        if hero.away_form_note else None,
        home_form_note=f"Regular-season form: {hero.home_form_note[0].lower()}{hero.home_form_note[1:]}"
        if hero.home_form_note else None)
    if info is None:
        series = {"round": game.round_name, "game": game.series_label,
                  "standing": game.series_summary, "stakes": game.series_stakes}
        hero = replace(hero, away_standing=_line(hero.away_standing, None),
                       home_standing=_line(hero.home_standing, None))
        return hero, series
    standing = None if info.standing.startswith("Best of") else info.standing
    series = {"round": info.round_name, "game": info.game_line,
              "standing": standing or f"Series opener · best of {info.series.best_of}",
              "stakes": info.stakes or ("If necessary" if info.if_necessary else None),
              "href": info.href}
    hero = replace(
        hero,
        away_standing=_line(hero.away_standing, info.seeds.get(str(game.away_id))),
        home_standing=_line(hero.home_standing, info.seeds.get(str(game.home_id))))
    return hero, series


def wnba_context(game: SlateGame, slate_date: date) -> dict:
    started = perf_counter()
    cache_key = (
        f"django:wnba-page:{WNBA_ENGINE_VERSION}:{slate_date.isoformat()}:{game.game_id}"
    )
    page = cache.get(cache_key)
    cache_source = "memory" if page is not None else None
    if page is None:
        page = matchup_cache.load(
            "WNBA", str(game.game_id), slate_date, WNBA_ENGINE_VERSION
        )
        if page is not None:
            cache.set(cache_key, page, timeout=900)
            cache_source = "database"
    if page is None:
        page = build_wnba_game_page(game, slate_date, slate_date)
        matchup_cache.store(
            "WNBA", str(game.game_id), slate_date, WNBA_ENGINE_VERSION, page
        )
        cache.set(cache_key, page, timeout=900)
        cache_source = "built"

    chunks = [
        wnba_components.hero_html(page.hero),
        wnba_components.game_script_html(page.game_script),
        wnba_components.snapshot_html(
            page.away_snapshot,
            page.home_snapshot,
            page.hero.away_team,
            page.hero.home_team,
        ),
        wnba_components.team_identity_html(page.away_identity, page.home_identity),
        wnba_components.battlefields_html(page.battlefields),
        wnba_components.shape_players_html(page.shape_players),
        wnba_components.trends_html(page.trending_up, page.trending_down),
        wnba_components.team_trends_html(page.away_trends, page.home_trends),
        wnba_components.opportunities_html(
            page.opportunities,
            {str(game.game_id): f"{game.away_display} @ {game.home_display}"},
        ),
        wnba_components.data_context_html(page.data_status.detail)
        if page.data_status and page.data_status.detail
        else "",
    ]
    return {
        "section": "today",
        "league": "WNBA",
        "game": game,
        "slate_date": slate_date,
        "day": "tomorrow" if slate_date > date.today() else "today",
        "content_chunks": [chunk for chunk in chunks if chunk],
        "cache_source": cache_source,
        "build_ms": round((perf_counter() - started) * 1000, 1),
    }


def mls_context(game: SlateGame, slate_date: date) -> dict:
    started = perf_counter()
    cache_key = f"django:mls-page:{MLS_ENGINE_VERSION}:{slate_date.isoformat()}:{game.game_id}"
    page = cache.get(cache_key)
    cache_source = "memory" if page is not None else None
    if page is None:
        page = matchup_cache.load("MLS", str(game.game_id), slate_date, MLS_ENGINE_VERSION)
        if page is not None:
            cache.set(cache_key, page, timeout=900)
            cache_source = "database"
    if page is None:
        page = build_mls_game_page(game, slate_date, slate_date)
        matchup_cache.store("MLS", str(game.game_id), slate_date, MLS_ENGINE_VERSION, page)
        cache.set(cache_key, page, timeout=900)
        cache_source = "built"

    chunks = [
        mls_components.hero_html(page.hero),
        mls_components.snapshot_html(
            page.snapshot, page.hero.away.short, page.hero.home.short
        ),
        mls_components.tactical_html(page.tactical),
        mls_components.storylines_html(page.storylines),
        mls_components.lineups_html(page.lineups),
        mls_components.players_html(page.players),
        mls_components.attacking_html(page.attacking),
        mls_components.discipline_html(page.discipline),
        mls_components.timeline_html(page.timeline),
        mls_components.honest_gaps_html(page.honest_gaps),
        mls_components.data_context_html(page.data_status.detail)
        if page.data_status and page.data_status.detail
        else "",
    ]
    return {
        "section": "today",
        "league": "MLS",
        "game": game,
        "slate_date": slate_date,
        "day": "tomorrow" if slate_date > date.today() else "today",
        "content_chunks": [chunk for chunk in chunks if chunk],
        "cache_source": cache_source,
        "build_ms": round((perf_counter() - started) * 1000, 1),
    }
