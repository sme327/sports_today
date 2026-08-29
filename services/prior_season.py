"""Last completed season, for leagues whose teams persist between them.

Answers one question for the editorial scorer: *how good were these two sides last
year?* It exists because the slate is unrankable without it for the first two weeks of a
season — every team is 0-0, `Standing.win_pct` is None below `MIN_GAMES`, and every
game scores 0. Measured on an opening-night NBA slate before this: Celtics-Lakers,
Hornets-Jazz and Wizards-Thunder all scored 0 and ranked identically. In January the
same three separate to 56, 41 and 35.

Read-only and defensive: any failure returns nothing, and the scorer then behaves
exactly as it did before. A missing table is the normal state on a fresh checkout.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from domain.models import SlateGame
from services.editorial import PriorSeason
from src.config import DB_PATH
from src.prior_season_collector import LEAGUES

# Cached per process: the slate asks the same handful of leagues about the same teams
# for every game on it, and a completed season cannot change under us.
_cache: dict[tuple[str, int], dict[str, PriorSeason]] = {}


def espn_season(slate_date: date) -> int:
    """The ESPN season year covering a date. Winter leagues name a season for the year
    it *ends* — 2026-10-21 belongs to season 2027 — so anything from September onward
    rolls forward."""
    return slate_date.year + 1 if slate_date.month >= 9 else slate_date.year


def prior_season_year(slate_date: date) -> int:
    return espn_season(slate_date) - 1


def load(league: str, season: int, db_path: Path = DB_PATH) -> dict[str, PriorSeason]:
    key = (league, season)
    if key in _cache and db_path == DB_PATH:
        return _cache[key]
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT team_id, wins, losses, ties, point_differential, team_name "
                "FROM prior_season_standings WHERE league = ? AND season = ?",
                (league, season)).fetchall()
    except sqlite3.Error:
        return {}
    table = {str(r[0]): PriorSeason(season=season, wins=int(r[1] or 0),
                                    losses=int(r[2] or 0), ties=int(r[3] or 0),
                                    point_differential=r[4], team_name=r[5])
             for r in rows}
    if db_path == DB_PATH:
        _cache[key] = table
    return table


def clear_cache() -> None:
    _cache.clear()


def pair_for(game: SlateGame, slate_date: date | None = None,
             db_path: Path = DB_PATH) -> tuple[PriorSeason | None, PriorSeason | None]:
    """(away, home) last-season records, or (None, None) when this league is not one we
    hold — which is every league except the pro schedule-only ones."""
    if game.league not in LEAGUES:
        return (None, None)
    when = slate_date or (game.start_time.date() if game.start_time else date.today())
    table = load(game.league, prior_season_year(when), db_path)
    if not table:
        return (None, None)
    meta = game.meta or {}
    away = table.get(str(meta.get("away_team_id") or ""))
    home = table.get(str(meta.get("home_team_id") or ""))
    return (away, home)
