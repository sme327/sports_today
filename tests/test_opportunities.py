import pandas as pd

from src.opportunity import score_hit_opportunities
from src.wnba_opportunity import score_wnba_opportunities


def test_mlb_empty_input_returns_empty_frame():
    empty = pd.DataFrame(columns=["batting_team", "game_date", "game_id", "pa_number"])
    result = score_hit_opportunities(empty, ["Seattle Mariners"])
    assert result.empty  # no crash, no sort on missing columns


def test_mlb_no_matching_teams_returns_empty():
    df = pd.DataFrame(
        {
            "batting_team": ["Seattle Mariners"] * 3,
            "game_date": ["2026-06-01", "2026-06-02", "2026-06-03"],
            "game_id": [1, 2, 3],
            "pa_number": [1, 1, 1],
            "batter_id": [10, 10, 10],
            "batter_name": ["A", "A", "A"],
            "is_hit": [1, 0, 1],
            "reached_base": [1, 0, 1],
            "is_strikeout": [0, 1, 0],
            "pitch_count_pa": [4, 3, 5],
        }
    )
    assert score_hit_opportunities(df, ["Houston Astros"]).empty


def test_wnba_empty_logs_returns_empty_frame():
    assert score_wnba_opportunities(pd.DataFrame(), {"SEA"}).empty


def test_wnba_no_scheduled_teams_returns_empty():
    logs = pd.DataFrame({"team_abbr": ["SEA"], "player_id": ["p1"]})
    assert score_wnba_opportunities(logs, set()).empty
