"""Data-freshness reporting for provenance display and diagnostics."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.config import DB_PATH
from services.data_access import table_exists


@dataclass(frozen=True)
class Freshness:
    mlb_through: date | None
    wnba_through: date | None
    wnba_collected_at: str | None


def _max_date(conn: sqlite3.Connection, table: str, column: str) -> str | None:
    if not table_exists(conn, table):
        return None
    row = conn.execute(f"SELECT MAX({column}) FROM {table}").fetchone()
    return row[0] if row else None


def get_freshness(db_path: Path = DB_PATH) -> Freshness:
    """Return the latest data dates for provenance labels. Never raises."""
    if not Path(db_path).exists():
        return Freshness(None, None, None)
    try:
        with sqlite3.connect(db_path) as conn:
            mlb_raw = _max_date(conn, "plate_appearances", "game_date")
            wnba_raw = _max_date(conn, "wnba_player_game_logs", "game_date")
            wnba_collected = _max_date(conn, "wnba_player_game_logs", "collected_at")
    except sqlite3.Error:
        return Freshness(None, None, None)

    def _to_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    return Freshness(
        mlb_through=_to_date(mlb_raw),
        wnba_through=_to_date(wnba_raw),
        wnba_collected_at=wnba_collected,
    )
