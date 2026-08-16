"""Persistent cache for immutable matchup page models.

Payloads are trusted application-generated pickles, keyed by the page engine version.
An engine change naturally misses the old row and builds a fresh model.
"""

from __future__ import annotations

import pickle
import sqlite3
from datetime import date, datetime
from pathlib import Path

from src.config import DB_PATH

_TABLE = "matchup_page_cache"


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            league TEXT NOT NULL,
            game_id TEXT NOT NULL,
            slate_date TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            calculated_at TEXT NOT NULL,
            payload BLOB NOT NULL,
            PRIMARY KEY (league, game_id, slate_date, engine_version)
        )
        """
    )


def load(league: str, game_id: str, slate_date: date, engine_version: str,
         *, db_path: Path = DB_PATH):
    if not Path(db_path).exists():
        return None
    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        row = conn.execute(
            f"""SELECT payload FROM {_TABLE}
                WHERE league=? AND game_id=? AND slate_date=? AND engine_version=?""",
            (league, str(game_id), slate_date.isoformat(), engine_version),
        ).fetchone()
    if not row:
        return None
    try:
        return pickle.loads(row[0])
    except (pickle.PickleError, EOFError, AttributeError, ValueError):
        return None


def store(league: str, game_id: str, slate_date: date, engine_version: str, page,
          *, db_path: Path = DB_PATH) -> None:
    payload = pickle.dumps(page, protocol=pickle.HIGHEST_PROTOCOL)
    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        conn.execute(
            f"""
            INSERT INTO {_TABLE}
                (league, game_id, slate_date, engine_version, calculated_at, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(league, game_id, slate_date, engine_version) DO UPDATE SET
                calculated_at=excluded.calculated_at,
                payload=excluded.payload
            """,
            (league, str(game_id), slate_date.isoformat(), engine_version,
             datetime.now().isoformat(timespec="seconds"), payload),
        )
        conn.commit()
