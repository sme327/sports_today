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

    chunks = [
        mlb_components.hero_html(page.hero),
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
        opportunities = opportunity_feed_html(list(page.opportunities))
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
        wnba_components.opportunities_html(page.opportunities),
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
