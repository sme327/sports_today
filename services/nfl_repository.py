"""Leakage-safe reads of the ingested NFL tables.

``as_of`` bounds every read to games strictly **before** that date, so a matchup
preview only ever uses what was known going into kickoff. Empty frames on a missing
DB/table — callers render honest awaiting-data states.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from src.config import DB_PATH


def _load(table: str, as_of: date | None, db_path: Path) -> pd.DataFrame:
    if not Path(db_path).exists():
        return pd.DataFrame()
    with sqlite3.connect(db_path) as conn:
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        except Exception:
            return pd.DataFrame()
    if as_of is not None and "game_date" in df.columns:
        df = df[df["game_date"].astype("string") < as_of.isoformat()]
    return df.reset_index(drop=True)


def load_team_games(as_of: date | None = None, db_path: Path = DB_PATH) -> pd.DataFrame:
    """Per-team-per-game rows (`nfl_team_games`), optionally `as_of`-bounded."""
    return _load("nfl_team_games", as_of, db_path)


def load_player_games(as_of: date | None = None, db_path: Path = DB_PATH) -> pd.DataFrame:
    """Per-player-per-game rows (`nfl_player_games`), optionally `as_of`-bounded."""
    return _load("nfl_player_games", as_of, db_path)


def load_teams(db_path: Path = DB_PATH) -> pd.DataFrame:
    """The team dimension (`nfl_teams`: initials, names, division, conference)."""
    return _load("nfl_teams", None, db_path)
