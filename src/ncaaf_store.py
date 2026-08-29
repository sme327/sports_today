"""SQLite schema + write helpers for the NCAAF season-context tables.

College football's problem is the opposite of MLB's: in Week 1 there is no current
season to read, and the schedule alone supports nothing — an editorial read on two 0-0
teams produces literally zero signals. What *is* knowable before kickoff is what each
team was last season, and how much of it is still there.

Additive tables only; nothing here touches an existing one. This module owns the DDL
and idempotent upserts and contains no network logic (that lives in
``src/ncaaf_collector.py``) and no rendering (``services/ncaaf_context.py``).

Honesty invariant: a missing provider value is written as NULL, never as zero. A team
with no prior-season row is a team we cannot describe, and the page must say so rather
than implying a 0-0 season.

**Roster membership is deliberately not stored.** The obvious way to ask "is last
season's quarterback still here?" is to hold each roster and look him up, and it is
wrong: ESPN's site roster endpoint truncates at exactly 100 players while real squads
run past 120, so anyone below the cut would read as departed. A false "he is gone" is
the worst error this feature can make. Asking the athlete where he plays now is one
request, cannot truncate, and answers the better question — it distinguishes a
transfer, with its destination, from a player who simply aged out.

**Head coaches are stored even though nothing reads them yet**, and that is deliberate.
ESPN has no historical coach: every season-scoped endpoint echoes today's coach
(Alabama returns Kalen DeBoer for 2022 and 2023, when it was Nick Saban), so
"new coach this year" cannot be derived from the provider at any price. It can only be
observed by writing down who the coach was and comparing later. The roster call already
returns the coach, so recording it costs nothing and makes the signal available from the
first season after this one — including an in-season change, which no provider field
would have given us either.
"""

from __future__ import annotations

import sqlite3

TEAM_SEASON_COLUMNS = (
    "season", "team_id", "team_name", "division", "conference",
    "overall", "wins", "losses", "collected_at",
)

PASSER_COLUMNS = (
    "season", "team_id", "athlete_id", "athlete_name", "position", "passing_yards",
    "status", "current_team_id", "collected_at",
)

COACH_COLUMNS = ("season", "team_id", "coach_id", "coach_name", "collected_at")


def ensure_tables(conn: sqlite3.Connection) -> None:
    """Idempotently create the NCAAF context tables. Safe on every run."""
    conn.executescript(
        """
        -- One row per team per completed season: the record the matchup page quotes,
        -- with its vintage. `division` separates FBS from FCS, which is the single
        -- biggest fact about an early-season college game.
        CREATE TABLE IF NOT EXISTS ncaaf_team_seasons (
            season INTEGER NOT NULL,
            team_id TEXT NOT NULL,
            team_name TEXT,
            division TEXT,
            conference TEXT,
            overall TEXT,
            wins INTEGER,
            losses INTEGER,
            collected_at TEXT,
            PRIMARY KEY (season, team_id)
        );

        -- That season's leading passer, and where he is now. Keyed by athlete id,
        -- never by name. `status` is one of 'returning', 'transferred' or 'inactive';
        -- `current_team_id` is set only for a transfer, and is what lets the page name
        -- the destination instead of just reporting an absence. NULL status means we
        -- could not check, which the page reports as unknown rather than as departure.
        CREATE TABLE IF NOT EXISTS ncaaf_team_passers (
            season INTEGER NOT NULL,
            team_id TEXT NOT NULL,
            athlete_id TEXT,
            athlete_name TEXT,
            position TEXT,
            passing_yards REAL,
            status TEXT,
            current_team_id TEXT,
            collected_at TEXT,
            PRIMARY KEY (season, team_id)
        );

        -- Written for the future, read by nothing today. See the module docstring.
        CREATE TABLE IF NOT EXISTS ncaaf_coaches (
            season INTEGER NOT NULL,
            team_id TEXT NOT NULL,
            coach_id TEXT,
            coach_name TEXT,
            collected_at TEXT,
            PRIMARY KEY (season, team_id)
        );
        """
    )


def _upsert(conn: sqlite3.Connection, table: str, columns: tuple[str, ...],
            rows: list[tuple]) -> int:
    if not rows:
        return 0
    placeholders = ", ".join("?" for _ in columns)
    sql = (f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) "
           f"VALUES ({placeholders})")
    conn.executemany(sql, rows)
    return len(rows)


def upsert_team_seasons(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    return _upsert(conn, "ncaaf_team_seasons", TEAM_SEASON_COLUMNS, rows)


def upsert_passers(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    return _upsert(conn, "ncaaf_team_passers", PASSER_COLUMNS, rows)


def upsert_coaches(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    return _upsert(conn, "ncaaf_coaches", COACH_COLUMNS, rows)
