"""SQLite schema + write helpers for MLS team-match data (Phase 3B).

Additive tables only; existing tables are never touched. This module owns the
DDL and idempotent upserts; it contains no ESPN/network logic (that lives in
``src/mls_collector.py``) and no Streamlit. Read-side queries live in
``services/mls_repository.py``.

Honesty invariant: writers pass ``None`` for a missing provider stat; the schema
stores NULL. Nothing here converts a missing value to zero.
"""

from __future__ import annotations

import sqlite3

# Column order is the contract for the upserts below.
MATCH_COLUMNS = (
    "event_id", "match_date", "kickoff_time", "season", "season_type",
    "competition_slug", "home_team_id", "away_team_id", "home_score",
    "away_score", "state", "venue_id", "venue", "attendance", "referee",
    "collected_at",
)

TEAM_STAT_COLUMNS = (
    "event_id", "team_id", "opponent_id", "is_home", "goals_for", "goals_against",
    "possession_pct", "total_shots", "shots_on_target", "shot_pct",
    "blocked_shots", "won_corners", "fouls_committed", "offsides", "saves",
    "yellow_cards", "red_cards", "total_passes", "accurate_passes", "pass_pct",
    "total_crosses", "accurate_crosses", "cross_pct", "total_tackles",
    "interceptions", "total_clearances", "pk_goals", "pk_shots", "collected_at",
)

STANDINGS_COLUMNS = (
    "season", "team_id", "snapshot_date", "conference", "conference_rank",
    "league_rank", "points", "games_played", "wins", "draws", "losses",
    "goals_for", "goals_against", "goal_difference", "collected_at",
)

EVENT_COLUMNS = (
    "match_id", "seq", "type", "category", "goal_source", "minute", "stoppage",
    "period", "bucket", "team_id", "primary_id", "primary_name",
    "secondary_id", "secondary_name", "collected_at",
)


def ensure_tables(conn: sqlite3.Connection) -> None:
    """Idempotently create the MLS tables + indexes. Safe on every startup."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS mls_matches (
            event_id TEXT PRIMARY KEY,
            match_date TEXT,
            kickoff_time TEXT,
            season INTEGER,
            season_type INTEGER,
            competition_slug TEXT,
            home_team_id TEXT,
            away_team_id TEXT,
            home_score INTEGER,
            away_score INTEGER,
            state TEXT,
            venue_id TEXT,
            venue TEXT,
            attendance INTEGER,
            referee TEXT,
            collected_at TEXT
        );

        CREATE TABLE IF NOT EXISTS mls_team_match_stats (
            event_id TEXT NOT NULL,
            team_id TEXT NOT NULL,
            opponent_id TEXT,
            is_home INTEGER,
            goals_for INTEGER,
            goals_against INTEGER,
            possession_pct REAL,
            total_shots INTEGER,
            shots_on_target INTEGER,
            shot_pct REAL,
            blocked_shots INTEGER,
            won_corners INTEGER,
            fouls_committed INTEGER,
            offsides INTEGER,
            saves INTEGER,
            yellow_cards INTEGER,
            red_cards INTEGER,
            total_passes INTEGER,
            accurate_passes INTEGER,
            pass_pct REAL,
            total_crosses INTEGER,
            accurate_crosses INTEGER,
            cross_pct REAL,
            total_tackles INTEGER,
            interceptions INTEGER,
            total_clearances INTEGER,
            pk_goals INTEGER,
            pk_shots INTEGER,
            collected_at TEXT,
            PRIMARY KEY (event_id, team_id)
        );

        CREATE INDEX IF NOT EXISTS idx_mls_stats_team ON mls_team_match_stats(team_id);
        CREATE INDEX IF NOT EXISTS idx_mls_matches_date ON mls_matches(match_date);

        -- Standings snapshot history: one row per team per collection day.
        CREATE TABLE IF NOT EXISTS mls_standings (
            season INTEGER NOT NULL,
            team_id TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            conference TEXT,
            conference_rank INTEGER,
            league_rank INTEGER,
            points INTEGER,
            games_played INTEGER,
            wins INTEGER,
            draws INTEGER,
            losses INTEGER,
            goals_for INTEGER,
            goals_against INTEGER,
            goal_difference INTEGER,
            collected_at TEXT,
            PRIMARY KEY (season, team_id, snapshot_date)
        );

        -- Match events (goals/cards/subs) for timeline + storyline signals.
        CREATE TABLE IF NOT EXISTS mls_match_events (
            match_id TEXT NOT NULL,
            seq TEXT NOT NULL,
            type TEXT,
            category TEXT,
            goal_source TEXT,
            minute INTEGER,
            stoppage INTEGER,
            period INTEGER,
            bucket TEXT,
            team_id TEXT,
            primary_id TEXT,
            primary_name TEXT,
            secondary_id TEXT,
            secondary_name TEXT,
            collected_at TEXT,
            PRIMARY KEY (match_id, seq)
        );

        CREATE INDEX IF NOT EXISTS idx_mls_events_match ON mls_match_events(match_id);
        CREATE INDEX IF NOT EXISTS idx_mls_events_team ON mls_match_events(team_id, category);

        CREATE TABLE IF NOT EXISTS mls_collection_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            finished_at TEXT,
            start_date TEXT,
            end_date TEXT,
            events_discovered INTEGER,
            events_skipped INTEGER,
            events_collected INTEGER,
            failures INTEGER,
            status TEXT,
            error_summary TEXT
        );
        """
    )


def _upsert(conn: sqlite3.Connection, table: str, columns: tuple[str, ...],
            rows: list[dict], key_columns: tuple[str, ...]) -> int:
    if not rows:
        return 0
    placeholders = ", ".join("?" for _ in columns)
    quoted = ", ".join(f'"{c}"' for c in columns)
    updates = ", ".join(f'"{c}"=excluded."{c}"' for c in columns if c not in key_columns)
    conflict = ", ".join(f'"{c}"' for c in key_columns)
    sql = (f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders}) '
           f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}")
    values = [tuple(row.get(c) for c in columns) for row in rows]
    conn.executemany(sql, values)
    return len(values)


def upsert_matches(conn: sqlite3.Connection, rows: list[dict]) -> int:
    return _upsert(conn, "mls_matches", MATCH_COLUMNS, rows, ("event_id",))


def upsert_team_stats(conn: sqlite3.Connection, rows: list[dict]) -> int:
    return _upsert(conn, "mls_team_match_stats", TEAM_STAT_COLUMNS, rows,
                   ("event_id", "team_id"))


def upsert_standings(conn: sqlite3.Connection, rows: list[dict]) -> int:
    return _upsert(conn, "mls_standings", STANDINGS_COLUMNS, rows,
                   ("season", "team_id", "snapshot_date"))


def upsert_events(conn: sqlite3.Connection, rows: list[dict]) -> int:
    return _upsert(conn, "mls_match_events", EVENT_COLUMNS, rows, ("match_id", "seq"))


def collected_event_ids(conn: sqlite3.Connection) -> set[str]:
    """Event IDs that already have both team-stat rows (a complete collection)."""
    rows = conn.execute(
        "SELECT event_id FROM mls_team_match_stats GROUP BY event_id HAVING COUNT(*) >= 2"
    ).fetchall()
    return {str(r[0]) for r in rows}


def fully_collected_event_ids(conn: sqlite3.Connection) -> set[str]:
    """Event IDs with **both** team stats and match events collected. Used as the
    incremental-skip set so matches that predate event collection get reprocessed
    (every match has at least substitution events)."""
    have_stats = collected_event_ids(conn)
    have_events = {str(r[0]) for r in conn.execute(
        "SELECT DISTINCT match_id FROM mls_match_events").fetchall()}
    return have_stats & have_events


def insert_run(conn: sqlite3.Connection, **fields) -> None:
    cols = ("started_at", "finished_at", "start_date", "end_date",
            "events_discovered", "events_skipped", "events_collected",
            "failures", "status", "error_summary")
    conn.execute(
        f"INSERT INTO mls_collection_runs ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' for _ in cols)})",
        tuple(fields.get(c) for c in cols),
    )
