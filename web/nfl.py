"""Django contexts for the NFL season archive and historical matchup pages."""

from __future__ import annotations

import sqlite3
from datetime import date
from time import perf_counter

from django.core.cache import cache

from components.nfl_game import page_html
from services import matchup_cache
from services.nfl_game_page import (
    ENGINE_VERSION,
    build_nfl_game_page,
    build_nfl_pregame_page,
)
from src.config import DB_PATH


def archive_context(params) -> dict:
    if not DB_PATH.exists():
        return {"section": "nfl", "seasons": [], "weeks": [], "games": []}
    try:
        with sqlite3.connect(DB_PATH) as conn:
            seasons = [
                int(row[0])
                for row in conn.execute(
                    "SELECT DISTINCT season FROM nfl_team_games "
                    "WHERE season IS NOT NULL ORDER BY season DESC"
                )
            ]
    except sqlite3.OperationalError:
        seasons = []
    context = {"section": "nfl", "seasons": seasons, "weeks": [], "games": []}
    if not seasons:
        return context

    try:
        season = int(params.get("season", seasons[0]))
    except (TypeError, ValueError):
        season = seasons[0]
    if season not in seasons:
        season = seasons[0]

    with sqlite3.connect(DB_PATH) as conn:
        weeks = [
            {"week": int(row[0]), "season_type": str(row[1]), "games": int(row[2])}
            for row in conn.execute(
                "SELECT week, season_type, COUNT(DISTINCT game_id) "
                "FROM nfl_team_games WHERE season=? "
                "GROUP BY week, season_type ORDER BY week",
                (season,),
            )
        ]
    available = [int(item["week"]) for item in weeks]
    if not available:
        return {**context, "season": season, "weeks": weeks}
    try:
        week = int(params.get("week", available[0]))
    except (TypeError, ValueError):
        week = available[0]
    if week not in available:
        week = available[0]

    for item in weeks:
        item["label"] = (
            f"WC {int(item['week'])}"
            if item["season_type"] == "postseason"
            else f"Wk {int(item['week'])}"
        )
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT game_id, MIN(game_date),
                   MAX(CASE WHEN venue='Road' THEN team END),
                   MAX(CASE WHEN venue='Home' THEN team END),
                   MAX(CASE WHEN venue='Road' THEN final END),
                   MAX(CASE WHEN venue='Home' THEN final END)
            FROM nfl_team_games WHERE season=? AND week=?
            GROUP BY game_id ORDER BY MIN(game_date), 3
            """,
            (season, week),
        ).fetchall()
    games = []
    for game_id, game_date, away, home, away_score, home_score in rows:
        a_score = int(away_score) if away_score is not None else None
        h_score = int(home_score) if home_score is not None else None
        games.append(
            {
                "game_id": str(game_id), "game_date": str(game_date),
                "away": str(away or "Away"), "home": str(home or "Home"),
                "away_score": a_score, "home_score": h_score,
                "away_won": a_score is not None and h_score is not None and a_score > h_score,
                "home_won": a_score is not None and h_score is not None and h_score > a_score,
            }
        )
    return {
        **context,
        "season": season,
        "week": week,
        "weeks": weeks,
        "games": games,
    }


def _game_date(game_id: str) -> date | None:
    if not DB_PATH.exists():
        return None
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT game_date FROM nfl_team_games WHERE game_id=? LIMIT 1",
            (str(game_id),),
        ).fetchone()
    if not row or not row[0]:
        return None
    try:
        return date.fromisoformat(str(row[0])[:10])
    except ValueError:
        return None


def matchup_context(game_id: str) -> dict | None:
    started = perf_counter()
    game_date = _game_date(game_id)
    if game_date is None:
        return None
    key = f"django:nfl-page:{ENGINE_VERSION}:{game_id}"
    page = cache.get(key)
    cache_source = "memory" if page is not None else None
    if page is None:
        page = matchup_cache.load("NFL", game_id, game_date, ENGINE_VERSION)
        if page is not None:
            cache.set(key, page, timeout=3600)
            cache_source = "database"
    if page is None:
        page = build_nfl_game_page(game_id)
        if page is None:
            return None
        matchup_cache.store("NFL", game_id, game_date, ENGINE_VERSION, page)
        cache.set(key, page, timeout=3600)
        cache_source = "built"
    return {
        "section": "nfl",
        "page": page,
        "content": page_html(page),
        "cache_source": cache_source,
        "build_ms": round((perf_counter() - started) * 1000, 1),
    }


def pregame_context(slate_game, slate_date: date) -> dict | None:
    """The matchup page for an **upcoming** slate game — built from aggregated data
    describing tonight's teams, never from a historical game (product rule,
    2026-08-21). Cached per slate date because the page sharpens daily as this
    season's played games arrive in the feed."""
    from services.nfl_bridge import canonical_team

    started = perf_counter()
    away = canonical_team(slate_game.away_name or slate_game.away_display)
    home = canonical_team(slate_game.home_name or slate_game.home_display)
    if not away or not home or away == home:
        return None
    phase = (slate_game.phase or "").lower()
    week = slate_game.week
    if phase == "preseason":
        round_label = f"Preseason · Wk {week}" if week else "Preseason"
    elif phase == "postseason":
        round_label = "Playoffs"
    else:
        round_label = f"Week {week}" if week else "Upcoming"
    kickoff = (slate_game.start_time.date() if slate_game.start_time else slate_date)

    cache_id = f"pre-{slate_game.game_id}"
    key = f"django:nfl-pregame:{ENGINE_VERSION}:{slate_date.isoformat()}:{slate_game.game_id}"
    page = cache.get(key)
    cache_source = "memory" if page is not None else None
    if page is None:
        page = matchup_cache.load("NFL", cache_id, slate_date, ENGINE_VERSION)
        if page is not None:
            cache.set(key, page, timeout=900)
            cache_source = "database"
    if page is None:
        page = build_nfl_pregame_page(away, home, kickoff.isoformat(), round_label,
                                      slate_game.season)
        if page is None:
            return None
        matchup_cache.store("NFL", cache_id, slate_date, ENGINE_VERSION, page)
        cache.set(key, page, timeout=900)
        cache_source = "built"
    return {
        "section": "nfl",
        "page": page,
        "content": page_html(page),
        "pregame": True,
        "cache_source": cache_source,
        "build_ms": round((perf_counter() - started) * 1000, 1),
    }
