"""Parser tests over a recorded-shape ESPN boxscore payload (no network)."""

from src.wnba_collector import (
    _clean_stat_name,
    _made_attempted,
    _minutes_float,
    _number,
    _parse_boxscore_players,
)


def test_stat_helpers():
    assert _made_attempted("7-12") == (7.0, 12.0)
    assert _made_attempted("--") == (None, None)
    assert _minutes_float("34:12") == 34.0 + 12.0 / 60.0
    assert _number("DNP") is None
    assert _number("18") == 18.0
    assert _clean_stat_name("PTS") == "points"
    assert _clean_stat_name("REB") == "rebounds"


_GAME = {
    "game_id": "g1", "game_date": "2026-06-01T00:00Z", "season": 2026, "season_type": 2,
    "home_team_id": "1", "home_team": "Home", "home_abbr": "HOM",
    "away_team_id": "2", "away_team": "Away", "away_abbr": "AWY",
}

_PAYLOAD = {
    "boxscore": {
        "players": [
            {
                "team": {"id": "1", "displayName": "Home", "abbreviation": "HOM"},
                "statistics": [
                    {
                        "labels": ["MIN", "FG", "3PT", "FT", "REB", "AST", "PTS"],
                        "athletes": [
                            {
                                "athlete": {"id": "99", "displayName": "Jane Hoop",
                                            "position": {"abbreviation": "G"}},
                                "starter": True, "active": True,
                                "stats": ["31:00", "8-15", "2-5", "4-4", "7", "6", "22"],
                            }
                        ],
                    }
                ],
            }
        ]
    }
}


def test_parse_boxscore_players_extracts_normalized_stats():
    rows = _parse_boxscore_players(_PAYLOAD, _GAME)
    assert len(rows) == 1
    row = rows[0]
    assert row["player_id"] == "99"
    assert row["player_name"] == "Jane Hoop"
    assert row["home_away"] == "home"
    assert row["points"] == 22.0
    assert row["rebounds"] == 7.0
    assert row["assists"] == 6.0
    assert row["minutes"] == 31.0
    assert row["opponent"] == "Away"  # opponent resolved from the game
