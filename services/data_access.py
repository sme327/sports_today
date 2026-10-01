"""Central, leakage-safe access to stored datasets.

Every historical window is bounded by an ``as_of`` slate date: only rows from
strictly before that date are returned, so scoring for a slate can never see
information from the slate date itself or later (owner decision 2). This makes
future-data leakage impossible by construction rather than by convention.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from src.config import DB_PATH


def _as_of_token(as_of: date | str | None) -> str | None:
    if as_of is None:
        return None
    return as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of)[:10]


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


POSTSEASON_MARK = "Postseason"


def is_postseason(pa: pd.DataFrame) -> pd.Series:
    """Rows from a postseason game. The vendor feed says so in ``dataset``
    ("MLB 2026 Postseason" against "MLB 2026 Regular Season")."""
    if pa.empty or "dataset" not in pa.columns:
        return pd.Series(False, index=pa.index)
    return pa["dataset"].astype(str).str.contains(POSTSEASON_MARK, case=False, na=False)


def load_plate_appearances(
    *,
    as_of: date | str | None = None,
    db_path: Path = DB_PATH,
    phase: str | None = None,
) -> pd.DataFrame:
    """Load MLB plate appearances, optionally bounded to before ``as_of``.

    ``game_date`` is stored as ``YYYY-MM-DD`` text, so the string comparison is a
    correct chronological bound. Returns an empty frame if the table is absent.

    ``phase`` is ``"regular"``, ``"postseason"`` or ``None`` (both). The feed carries
    postseason games in the same table, so a caller describing *the season* must ask for
    ``"regular"`` — otherwise a Wild Card game quietly becomes game 163 of it, which is
    how the matchup page came to say "163 games" (decision log 2026-09-30). The prop
    scorers deliberately still read both: they are versioned engines graded on the
    Performance page, and changing their inputs is a backtest, not a filter.
    """
    if not Path(db_path).exists():
        return pd.DataFrame()
    token = _as_of_token(as_of)
    with sqlite3.connect(db_path) as conn:
        if not table_exists(conn, "plate_appearances"):
            return pd.DataFrame()
        if token is None:
            df = pd.read_sql_query("SELECT * FROM plate_appearances", conn)
        else:
            df = pd.read_sql_query(
                "SELECT * FROM plate_appearances WHERE game_date < ?",
                conn,
                params=[token],
            )
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"])
        if phase == "regular":
            df = df[~is_postseason(df)].reset_index(drop=True)
        elif phase == "postseason":
            df = df[is_postseason(df)].reset_index(drop=True)
    return df


def load_wnba_player_logs(
    *,
    as_of: date | str | None = None,
    db_path: Path = DB_PATH,
) -> pd.DataFrame:
    """Load WNBA player game logs, optionally bounded to before ``as_of``.

    ``game_date`` here is an ISO timestamp, so we compare on its date prefix.
    Returns an empty frame if the table is absent.
    """
    if not Path(db_path).exists():
        return pd.DataFrame()
    token = _as_of_token(as_of)
    with sqlite3.connect(db_path) as conn:
        if not table_exists(conn, "wnba_player_game_logs"):
            return pd.DataFrame()
        if token is None:
            return pd.read_sql_query(
                "SELECT * FROM wnba_player_game_logs ORDER BY game_date, game_id",
                conn,
            )
        return pd.read_sql_query(
            """
            SELECT *
            FROM wnba_player_game_logs
            WHERE substr(game_date, 1, 10) < ?
            ORDER BY game_date, game_id
            """,
            conn,
            params=[token],
        )
