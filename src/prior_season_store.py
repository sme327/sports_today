"""SQLite schema + upserts for completed-season records, across leagues.

One table rather than a per-league one: unlike `ncaaf_team_seasons`, which carries a
division and a conference because college football's structure is the story, the pro
leagues need only "how good were they last year". A shared table keeps the read side a
single query and makes adding a league a config entry rather than a migration.

Why the pro leagues get this at all, and college does not use it for ranking: measured
2026-08-29, the same team's key player is still there for 90% of NBA teams and 100% of
NHL teams, against 41% in college football. Pro rosters persist, so last season
describes roughly the same team; a college team's record describes a team that has
largely left. The number that made the college turnover signal worth building is the
same number that makes this fallback safe there and unsafe in college.
"""

from __future__ import annotations

import sqlite3

STANDING_COLUMNS = (
    "league", "season", "team_id", "team_name", "wins", "losses", "ties",
    "point_differential", "collected_at",
)


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS prior_season_standings (
            league TEXT NOT NULL,
            season INTEGER NOT NULL,
            team_id TEXT NOT NULL,
            team_name TEXT,
            wins INTEGER,
            losses INTEGER,
            ties INTEGER,
            -- Points/goals per game above or below the opposition. Published by the
            -- pro leagues and not by college football; NULL where the source omits it,
            -- never zero, because zero is a real and different claim.
            point_differential REAL,
            collected_at TEXT,
            PRIMARY KEY (league, season, team_id)
        );
        """
    )


def upsert_standings(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    if not rows:
        return 0
    placeholders = ", ".join("?" for _ in STANDING_COLUMNS)
    conn.executemany(
        f"INSERT OR REPLACE INTO prior_season_standings "
        f"({', '.join(STANDING_COLUMNS)}) VALUES ({placeholders})", rows)
    return len(rows)
