"""Offline tests for NFL analytics — synthetic per-game frames (no DB, no network).
Covers opponent-paired 'allowed' derivation, season profile + percentiles, and
head-to-head battlefields."""

from __future__ import annotations

import pandas as pd

from services.nfl_analytics import (
    battlefields, player_game_frame, rest_days, team_game_frame, team_season_table,
)


def _tg(game_id, team, opponent, week, points, pass_yds, rush_yds):
    return {
        "game_id": game_id, "game_date": f"2025-09-{week:02d}", "week": week,
        "season_type": "regular", "team": team, "opponent": opponent,
        "final": points, "yards_total_yards": pass_yds + rush_yds,
        "passing_yds": pass_yds, "rushing_yds": rush_yds, "total_plays": 65,
        "passing_att": 32, "rushing_rush": 26, "passing_comp": 20,
        "turnovers_penalties_turnovers": 1, "third_downs_made": 6, "third_downs_att": 14,
        "first_downs": 22, "sacks_sacked": 2, "passing_int": 1,
    }


# A four-team, four-game slice: A/B play twice, C/D play twice.
_TEAM = pd.DataFrame([
    _tg("g1", "A", "B", 1, 30, 300, 100), _tg("g1", "B", "A", 1, 20, 250, 90),
    _tg("g2", "A", "B", 2, 24, 260, 120), _tg("g2", "B", "A", 2, 27, 280, 110),
    _tg("g3", "C", "D", 1, 17, 200, 130), _tg("g3", "D", "C", 1, 14, 190, 80),
    _tg("g4", "C", "D", 2, 21, 220, 140), _tg("g4", "D", "C", 2, 28, 300, 95),
])


def test_allowed_is_the_opponents_offense():
    frame = team_game_frame(_TEAM)
    a_g1 = frame[(frame.game_id == "g1") & (frame.team == "A")].iloc[0]
    assert a_g1.points == 30 and a_g1.points_allowed == 20      # B scored 20 → A allowed 20
    assert a_g1.pass_yds_allowed == 250                          # B's passing
    assert a_g1.win == 1


def test_season_table_profiles_and_percentiles():
    t = team_season_table(team_game_frame(_TEAM))
    assert len(t) == 4
    a = t.loc["A"]
    assert a["points"] == 27.0 and a["points_allowed"] == 23.5   # (30+24)/2, (20+27)/2
    assert round(a["net_points"], 1) == 3.5
    # percentiles present and in range
    for col in ("off_pct", "def_pct", "pass_off_pct", "rush_def_pct"):
        assert 0 <= int(t[col].max()) <= 100


def test_battlefields_pair_offense_vs_defense():
    t = team_season_table(team_game_frame(_TEAM))
    bfs = battlefields(t, "A", "B", "A", "B")
    assert len(bfs) == 4
    first = bfs[0]
    assert "pass offense vs" in first.label
    assert first.edge in {"Edge A", "Edge B", "Even"}


def _rest_frame() -> pd.DataFrame:
    """One team on a normal week, then a short week, then off a bye."""
    return pd.DataFrame([
        {"team": "A", "game_date": "2025-09-07"},   # opener
        {"team": "A", "game_date": "2025-09-14"},   # +7 — normal week
        {"team": "A", "game_date": "2025-09-18"},   # +4 — short week (Thursday)
        {"team": "A", "game_date": "2025-10-05"},   # +17 — off a bye
        {"team": "B", "game_date": "2025-09-28"},   # another team, must not leak in
    ])


def test_rest_days_counts_from_the_previous_game():
    tg = _rest_frame()
    assert rest_days(tg, "A", "2025-09-14") == 7
    assert rest_days(tg, "A", "2025-09-18") == 4     # short week
    assert rest_days(tg, "A", "2025-10-05") == 17    # off a bye


def test_rest_days_is_none_for_a_season_opener():
    # Nothing strictly before the opener → no rest figure to report (never 0).
    assert rest_days(_rest_frame(), "A", "2025-09-07") is None


def test_rest_days_ignores_other_teams_and_later_games():
    tg = _rest_frame()
    # B's only game sits between two of A's; it must not become A's "previous game".
    assert rest_days(tg, "A", "2025-10-05") == 17
    # A team with no games at all has no rest figure.
    assert rest_days(tg, "Z", "2025-10-05") is None


def test_rest_days_none_on_unparseable_date():
    assert rest_days(_rest_frame(), "A", "not-a-date") is None


def test_player_frame_types_and_filters():
    pg = pd.DataFrame([
        {"game_id": "g1", "game_date": "2025-09-07", "week": 1, "player_id": "d-henry",
         "player": "Derrick Henry", "position": "RB", "team": "A", "opponent": "B",
         "rushing_att": "20", "rushing_yds": "126", "rushing_td": "1",
         "receiving_rec": "2", "receiving_yds": "15"},
        {"game_id": "g2", "game_date": "2025-09-14", "week": 2, "player_id": "d-henry",
         "player": "Derrick Henry", "position": "RB", "team": "A", "opponent": "B",
         "rushing_att": "18", "rushing_yds": "94", "rushing_td": "0",
         "receiving_rec": "1", "receiving_yds": "8"},
    ])
    pf = player_game_frame(pg, team="A")
    assert len(pf) == 2 and pf.iloc[0].week == 2                 # newest first
    assert pf.iloc[0].rushing_yds == 94                          # coerced to numeric
    assert player_game_frame(pg, team="Z").empty
