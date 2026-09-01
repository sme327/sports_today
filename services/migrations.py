"""Guarded, additive schema setup for Sports Today's SQLite database.

Creates only the new tables this refactor introduces (schedule_cache,
opportunity_snapshots) and a schema_version marker. Existing tables
(plate_appearances, players, games, wnba_*) are never touched.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.config import DB_PATH
from services import daily_feed, matchup_cache, schedule_cache, snapshots
from src import mls_store

SCHEMA_VERSION = 2
# v2 (2026-08-31): backfill opportunity_snapshots.opponent on rows captured before that
# column existed. Version-gated rather than run on every boot: ~500 of those rows predate
# game_id itself and can never be filled, so a "retry while any are blank" guard would
# re-scan the ledger forever.


def ensure_schema(db_path: Path = DB_PATH) -> None:
    """Idempotently ensure new tables exist. Safe to call on every startup."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL,
                applied_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        schedule_cache.ensure_table(conn)
        snapshots.ensure_table(conn)
        daily_feed.ensure_table(conn)
        matchup_cache.ensure_table(conn)
        mls_store.ensure_tables(conn)

        current = conn.execute(
            "SELECT version FROM schema_version WHERE id = 1").fetchone()
        if (current[0] if current else 0) < 2:
            filled = snapshots._backfill_opponents(conn)
            if filled:
                print(f"Backfilled opponent on {filled:,} snapshot rows.")

        conn.execute(
            "INSERT OR REPLACE INTO schema_version (id, version) VALUES (1, ?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()
