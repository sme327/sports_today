"""Persistent cache of fetched schedules.

The cache is consulted *before* any league-wide fallback so that a brief upstream
hiccup never changes the meaning of the homepage (owner refinement). Each row
records league, slate date, fetch timestamp, source, success/failure status, and
the normalized games as JSON (section 3.1).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from src.config import DB_PATH
from domain.models import SlateGame, SourceStatus

_TABLE = "schedule_cache"


def _slate_token(slate_date: date | str) -> str:
    return slate_date.isoformat() if hasattr(slate_date, "isoformat") else str(slate_date)[:10]


def game_to_dict(game: SlateGame) -> dict:
    data = dict(game.__dict__)
    start = data.get("start_time")
    data["start_time"] = start.isoformat() if isinstance(start, datetime) else start
    return data


def game_from_dict(data: dict) -> SlateGame:
    data = dict(data)
    start = data.get("start_time")
    if isinstance(start, str):
        try:
            data["start_time"] = datetime.fromisoformat(start)
        except ValueError:
            data["start_time"] = None
    data.setdefault("meta", {})
    return SlateGame(**data)


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            league TEXT NOT NULL,
            slate_date TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            source TEXT,
            status TEXT NOT NULL,
            game_count INTEGER NOT NULL DEFAULT 0,
            payload TEXT,
            PRIMARY KEY (league, slate_date, fetched_at)
        )
        """
    )


def write(
    *,
    league: str,
    slate_date: date | str,
    source: str,
    status: SourceStatus,
    games: list[SlateGame],
    fetched_at: datetime | None = None,
    db_path: Path = DB_PATH,
) -> None:
    """Record a successful fetch (including legitimately-empty results)."""
    fetched_at = fetched_at or datetime.now()
    payload = json.dumps([game_to_dict(g) for g in games])
    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        conn.execute(
            f"""
            INSERT OR REPLACE INTO {_TABLE}
                (league, slate_date, fetched_at, source, status, game_count, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                league,
                _slate_token(slate_date),
                fetched_at.isoformat(timespec="seconds"),
                source,
                status.value,
                len(games),
                payload,
            ),
        )
        conn.commit()


def read_latest_usable(
    *,
    league: str,
    slate_date: date | str,
    db_path: Path = DB_PATH,
) -> tuple[list[SlateGame], datetime] | None:
    """Return the most recent cached slate with at least one game, or None.

    Only rows with ``game_count > 0`` qualify: a cached empty result is not a
    usable slate to fall back to.
    """
    if not Path(db_path).exists():
        return None
    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        row = conn.execute(
            f"""
            SELECT payload, fetched_at
            FROM {_TABLE}
            WHERE league = ? AND slate_date = ? AND game_count > 0
            ORDER BY fetched_at DESC
            LIMIT 1
            """,
            (league, _slate_token(slate_date)),
        ).fetchone()
    if not row or not row[0]:
        return None
    try:
        games = [game_from_dict(d) for d in json.loads(row[0])]
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        fetched = datetime.fromisoformat(row[1])
    except (ValueError, TypeError):
        fetched = datetime.now()
    return games, fetched
