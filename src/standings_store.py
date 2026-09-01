"""Current-season standings: the reference point a style read cannot give you.

**Why this exists.** The MLB matchup page describes *how* a team plays — power, contact,
plate discipline, speed — and never says whether they are any good. A reader looking at
two slider stacks has no way to turn them into wins, because nothing on the page is
denominated in wins. Records, division position and games back are that anchor, and the
same rows answer a standings page and, later, playoff seeding.

Distinct from ``prior_season_standings``, which holds *completed* seasons for ranking an
opening-night slate and is written once per season. These rows change daily and are
replaced daily, keyed by ``snapshot_date`` so a page built for a past date still reads
the standings as they were.

Distinct again from ``mls_standings``, which predates this and carries soccer's own
shape (points, draws, goal difference). Not merged: a table that has to serve both
points-per-draw and games-behind ends up honest about neither. MLS keeps its own.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.config import DB_PATH

TABLE = "league_standings"

COLUMNS = (
    "league", "season", "snapshot_date", "team_id", "team_name", "team_abbr",
    "conference", "division", "division_rank", "wins", "losses", "ties",
    "win_pct", "games_behind", "playoff_seed", "streak", "last_ten",
    "home_record", "road_record", "collected_at",
)


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            league TEXT NOT NULL,
            season INTEGER NOT NULL,
            snapshot_date TEXT NOT NULL,
            team_id TEXT NOT NULL,
            team_name TEXT,
            team_abbr TEXT,
            conference TEXT,
            division TEXT,
            division_rank INTEGER,
            wins INTEGER,
            losses INTEGER,
            ties INTEGER,
            win_pct REAL,
            games_behind REAL,
            playoff_seed INTEGER,
            streak TEXT,
            last_ten TEXT,
            home_record TEXT,
            road_record TEXT,
            collected_at TEXT,
            PRIMARY KEY (league, season, snapshot_date, team_id)
        )
        """
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_lookup "
        f"ON {TABLE} (league, snapshot_date)"
    )


def upsert(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Replace a day's standings for the leagues present. Idempotent per day."""
    if not rows:
        return 0
    placeholders = ", ".join("?" for _ in COLUMNS)
    conn.executemany(
        f"INSERT OR REPLACE INTO {TABLE} ({', '.join(COLUMNS)}) VALUES ({placeholders})",
        [tuple(row.get(col) for col in COLUMNS) for row in rows],
    )
    return len(rows)


def latest_snapshot(conn: sqlite3.Connection, league: str,
                    on_or_before: str | None = None) -> str | None:
    """The most recent stored date for a league, never later than ``on_or_before``.

    The bound is the ``as_of`` rule: a page built for a past slate must read the
    standings as they stood then, not as they stand now — otherwise a matchup page
    rebuilt in October would describe an August game with October's records.
    """
    if on_or_before:
        row = conn.execute(
            f"SELECT MAX(snapshot_date) FROM {TABLE} "
            f"WHERE league = ? AND snapshot_date <= ?", (league, on_or_before)).fetchone()
    else:
        row = conn.execute(
            f"SELECT MAX(snapshot_date) FROM {TABLE} WHERE league = ?", (league,)).fetchone()
    return row[0] if row and row[0] else None


def load(league: str, snapshot_date: str | None = None,
         db_path: Path = DB_PATH) -> list[dict]:
    """Standings rows for a league on a date (default: the latest stored)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            token = snapshot_date or latest_snapshot(conn, league)
            if not token:
                return []
            rows = conn.execute(
                f"SELECT * FROM {TABLE} WHERE league = ? AND snapshot_date = ? "
                f"ORDER BY division, division_rank", (league, token)).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(r) for r in rows]
