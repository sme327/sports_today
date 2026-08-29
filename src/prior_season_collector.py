"""Fetch completed-season standings for the pro schedule-only leagues.

Cheap and rare: 32 NHL teams and 30 NBA teams in two requests, for a fact that cannot
change once the season is over. The daily run refreshes it only when the stored season
is missing.

`ties` carries the sport's third outcome where it has one — NHL overtime losses count
as neither a win nor a win-and-a-half, but they are games played, and dropping them
would inflate every team's win percentage.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.config import DB_PATH
from src.ncaaf_collector import fetch_json
from src.prior_season_store import ensure_tables, upsert_standings

STANDINGS = "https://site.api.espn.com/apis/v2/sports"


@dataclass(frozen=True)
class LeagueSpec:
    """Where a league's standings live, and what its third outcome is called."""

    path: str                       # ESPN sport/league path, e.g. "hockey/nhl"
    ties_stat: str | None = None    # stat name counted as neither win nor loss
    differential_stat: str | None = "differential"


# Deliberately only the leagues whose rosters persist. NCAAF is absent by design: see
# src/prior_season_store for the measurement that makes this safe here and not there.
LEAGUES: dict[str, LeagueSpec] = {
    "NHL": LeagueSpec("hockey/nhl", ties_stat="otLosses"),
    "NBA": LeagueSpec("basketball/nba"),
}


def _stat(entry: dict, name: str) -> float | None:
    for stat in entry.get("stats") or []:
        if stat.get("name") == name:
            value = stat.get("value")
            try:
                return float(value)                              # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None
    return None


def league_standings(league: str, season: int) -> list[tuple]:
    spec = LEAGUES.get(league)
    if spec is None:
        return []
    payload = fetch_json(f"{STANDINGS}/{spec.path}/standings?season={season}")
    if not payload:
        return []
    now = datetime.now().isoformat(timespec="seconds")
    rows: list[tuple] = []

    def walk(node: dict) -> None:
        for entry in (node.get("standings") or {}).get("entries") or []:
            team = entry.get("team") or {}
            wins, losses = _stat(entry, "wins"), _stat(entry, "losses")
            if wins is None or losses is None:
                continue
            ties = _stat(entry, spec.ties_stat) if spec.ties_stat else None
            rows.append((league, season, str(team.get("id")), team.get("displayName"),
                         int(wins), int(losses), int(ties or 0),
                         _stat(entry, spec.differential_stat or ""), now))
        for child in node.get("children") or []:
            walk(child)

    walk(payload)
    return rows


def collect(*, season: int, leagues: list[str] | None = None,
            db_path: Path = DB_PATH) -> dict:
    """Store each league's completed-season standings. Returns per-league row counts."""
    summary: dict[str, int] = {}
    with sqlite3.connect(db_path) as conn:
        ensure_tables(conn)
        for league in (leagues or list(LEAGUES)):
            rows = league_standings(league, season)
            summary[league] = upsert_standings(conn, rows)
        conn.commit()
    return summary


def have_season(league: str, season: int, db_path: Path = DB_PATH) -> bool:
    """Whether the completed season is already stored — the whole refresh check, since
    a finished season's record never changes."""
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM prior_season_standings "
                "WHERE league = ? AND season = ?", (league, season)).fetchone()
    except sqlite3.Error:
        return False
    return bool(row and row[0])
