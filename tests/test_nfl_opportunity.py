"""Offline tests for NFL player-prop selection (reachable-bar, by position)."""

from __future__ import annotations

import pandas as pd

from src.nfl_opportunity import best_prop, key_players


def _games(position, **stat_vals):
    """Build a player's game log from lists of per-game stat values."""
    n = len(next(iter(stat_vals.values())))
    rows = []
    for i in range(n):
        row = {"game_date": f"2025-09-{i + 1:02d}", "player_id": "p1", "player": "Player One",
               "position": position}
        for stat, vals in stat_vals.items():
            row[stat] = vals[i]
        rows.append(row)
    return pd.DataFrame(rows)


def test_best_prop_picks_highest_reachable_bar():
    rb = _games("RB", rushing_yds=[80, 90, 50, 70, 65, 85])   # 60+ in 5/6, 75+ in only 3/6
    prop = best_prop(rb, "RB")
    assert prop is not None
    assert prop["stat"] == "rushing_yds" and prop["threshold"] == 60
    assert prop["label"] == "Rush Yards" and prop["clear_rate"] >= 0.55


def test_best_prop_needs_enough_games():
    assert best_prop(_games("RB", rushing_yds=[80, 90, 70]), "RB") is None   # 3 < MIN_GAMES


def test_best_prop_none_when_no_reachable_bar():
    # A low-volume receiver clears no meaningful bar in ≥55% of games.
    wr = _games("WR", receiving_yds=[10, 0, 20, 5, 15, 8])
    assert best_prop(wr, "WR") is None


def test_key_players_picks_qb_rb_and_receivers():
    df = pd.DataFrame([
        {"player_id": "qb", "player": "QB", "position": "QB", "passing_att": 34,
         "rushing_att": 3, "receiving_tar": 0},
        {"player_id": "rb", "player": "RB", "position": "RB", "passing_att": 0,
         "rushing_att": 18, "receiving_tar": 2},
        {"player_id": "wr1", "player": "WR1", "position": "WR", "passing_att": 0,
         "rushing_att": 0, "receiving_tar": 9},
        {"player_id": "wr2", "player": "WR2", "position": "WR", "passing_att": 0,
         "rushing_att": 0, "receiving_tar": 6},
        {"player_id": "wr3", "player": "WR3", "position": "WR", "passing_att": 0,
         "rushing_att": 0, "receiving_tar": 1},   # too few targets → excluded
    ])
    ids = {p[0] for p in key_players(df)}
    assert {"qb", "rb", "wr1", "wr2"} <= ids and "wr3" not in ids
