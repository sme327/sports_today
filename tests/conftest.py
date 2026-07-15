"""Shared test fixtures. No test requires network access."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """A temp SQLite DB seeded with a tiny plate_appearances + WNBA logs sample."""
    db = tmp_path / "test.db"
    pa = pd.DataFrame(
        {
            "game_id": [1, 1, 2, 2, 3, 3],
            "game_date": [
                "2026-06-01", "2026-06-01",
                "2026-06-05", "2026-06-05",
                "2026-06-10", "2026-06-10",
            ],
            "batting_team": [
                "Seattle Mariners", "Houston Astros",
                "Seattle Mariners", "Houston Astros",
                "Seattle Mariners", "Houston Astros",
            ],
            "pitching_team": [
                "Houston Astros", "Seattle Mariners",
                "Houston Astros", "Seattle Mariners",
                "Houston Astros", "Seattle Mariners",
            ],
            "batter_id": [10, 20, 10, 20, 10, 20],
            "batter_name": ["A", "B", "A", "B", "A", "B"],
            "is_hit": [1, 0, 1, 1, 0, 1],
            "total_bases": [1, 0, 2, 1, 0, 4],
            "is_walk": [0, 0, 0, 0, 1, 0],
            "is_strikeout": [0, 1, 0, 0, 0, 0],
            "is_home_run": [0, 0, 0, 0, 0, 1],
            "reached_base": [1, 0, 1, 1, 1, 1],
            "pitch_count_pa": [4, 3, 5, 4, 6, 4],
            "pa_number": [1, 1, 1, 1, 1, 1],
        }
    )
    wnba = pd.DataFrame(
        {
            "game_id": ["g1", "g2"],
            "player_id": ["p1", "p1"],
            "game_date": ["2026-06-01T00:00Z", "2026-06-08T00:00Z"],
            "player_name": ["Star", "Star"],
            "team_id": ["1", "1"],
            "team": ["Seattle Storm", "Seattle Storm"],
            "team_abbr": ["SEA", "SEA"],
            "minutes": [30.0, 32.0],
            "points": [22.0, 18.0],
            "rebounds": [6.0, 7.0],
            "assists": [4.0, 5.0],
            "collected_at": ["2026-06-02T00:00Z", "2026-06-09T00:00Z"],
        }
    )
    with sqlite3.connect(db) as conn:
        pa.to_sql("plate_appearances", conn, index=False)
        wnba.to_sql("wnba_player_game_logs", conn, index=False)
    return db
