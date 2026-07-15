"""Guarded, additive schema setup for Sports Hub's SQLite database.

Creates only the new tables this refactor introduces (schedule_cache,
opportunity_snapshots) and a schema_version marker. Existing tables
(plate_appearances, players, games, wnba_*) are never touched.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.config import DB_PATH
from services import schedule_cache, snapshots

SCHEMA_VERSION = 1


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
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (id, version) VALUES (1, ?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()
