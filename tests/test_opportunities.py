import pandas as pd

from src.mlb_lineups import Lineups
from src.opportunity import score_hit_opportunities
from src.wnba_opportunity import score_wnba_opportunities


def _batter_pa(bid, team, n_games=12, pa_per=4):
    """A batter with enough PAs to clear the minimum, ~1 hit per game."""
    rows = []
    for g in range(n_games):
        for p in range(pa_per):
            got = 1 if p == 0 else 0
            rows.append({"batting_team": team, "game_date": f"2026-06-{g + 1:02d}",
                         "game_id": g, "pa_number": p + 1, "batter_id": bid,
                         "batter_name": f"Batter {bid}", "is_hit": got, "reached_base": got,
                         "is_strikeout": 0, "pitch_count_pa": 4})
    return pd.DataFrame(rows)


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


def test_lineup_confirmed_slot_adds_evidence():
    pa = _batter_pa(10, "Seattle Mariners")
    lineups = Lineups(slot={10: 3}, posted_teams=frozenset({"Seattle Mariners"}))
    r = score_hit_opportunities(pa, ["Seattle Mariners"], lineups=lineups)
    row = r.iloc[0]
    assert row.lineup_slot == 3
    assert "Batting 3rd, confirmed lineup" in row.support
    assert "Not in today's posted lineup" not in row.risks


def test_lineup_bench_caps_score():
    pa = _batter_pa(10, "Seattle Mariners")           # strong history
    lineups = Lineups(slot={}, posted_teams=frozenset({"Seattle Mariners"}))  # team out, bat scratched
    r = score_hit_opportunities(pa, ["Seattle Mariners"], lineups=lineups)
    row = r.iloc[0]
    assert row.risks[0] == "Not in today's posted lineup"
    assert row.opportunity_score <= 25
    assert row.stability_score <= 40


def test_lineup_not_posted_is_honest():
    pa = _batter_pa(10, "Seattle Mariners")
    lineups = Lineups(slot={}, posted_teams=frozenset())   # nothing posted yet
    r = score_hit_opportunities(pa, ["Seattle Mariners"], lineups=lineups)
    row = r.iloc[0]
    assert "Lineup not yet posted" in row.risks
    assert row.opportunity_score > 25                       # not penalized for missing data


def test_no_lineups_is_backward_compatible():
    pa = _batter_pa(10, "Seattle Mariners")
    r = score_hit_opportunities(pa, ["Seattle Mariners"])   # no lineups arg
    row = r.iloc[0]
    assert row.lineup_slot is None
    assert not any("posted" in s for s in row.support)
    assert "Opponent and confirmed lineup context not yet included" in row.risks


def test_wnba_empty_logs_returns_empty_frame():
    assert score_wnba_opportunities(pd.DataFrame(), {"SEA"}).empty


def test_wnba_no_scheduled_teams_returns_empty():
    logs = pd.DataFrame({"team_abbr": ["SEA"], "player_id": ["p1"]})
    assert score_wnba_opportunities(logs, set()).empty
