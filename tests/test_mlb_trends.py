"""Offline tests for the MLB trend spotlights (pitcher per-start + batter per-game).
Synthetic plate appearances — no network, no DB."""

from __future__ import annotations

import pandas as pd

from components import mlb_game as C
from services import mlb_trends as T


def _pitcher_pa(pid, per_start):
    """per_start: list of (k, hits) per start. Each start faces ≥ 10 batters (1T PA)."""
    rows = []
    for gi, (k, h) in enumerate(per_start):
        gid = f"g{gi}"
        day = f"2026-06-{gi + 1:02d}"
        rows.append((pid, "Ace", "Team", gid, day, "1T", 0, 0))
        for i in range(14):
            rows.append((pid, "Ace", "Team", gid, day, "3T",
                         1 if i < k else 0, 1 if k <= i < k + h else 0))
    return pd.DataFrame(rows, columns=["pitcher_id", "pitcher_name", "pitching_team",
                                       "game_id", "game_date", "inning", "is_strikeout", "is_hit"])


def _batter_pa(bid, per_game_hits):
    """per_game_hits: list of 0/1 (did they hit that game)."""
    rows = []
    for gi, got in enumerate(per_game_hits):
        gid = f"g{gi}"
        day = f"2026-06-{gi + 1:02d}"
        for pa_n in range(4):
            rows.append((bid, "Slugger", "Team", gid, day, pa_n, 1 if (got and pa_n == 0) else 0))
    return pd.DataFrame(rows, columns=["batter_id", "batter_name", "batting_team",
                                       "game_id", "game_date", "pa_number", "is_hit"])


def test_pitcher_trend_sparklines_and_props():
    pa = _pitcher_pa("1", [(6, 4), (7, 5), (5, 3), (6, 4), (8, 2)])
    t = T.pitcher_trend(pa, "1")
    assert t is not None and t.starts == 5
    assert t.k_spark == (6, 7, 5, 6, 8) and t.hits_spark == (4, 5, 3, 4, 2)  # oldest → newest
    assert t.k_avg == 6.4 and t.props                                        # served SP props exist
    assert t.k_pct is not None


def test_pitcher_trend_requires_starts():
    assert T.pitcher_trend(_pitcher_pa("1", [(6, 4), (7, 5)]), "1") is None   # 2 < MIN_STARTS


def test_pitcher_trend_direction():
    down = T.pitcher_trend(_pitcher_pa("1", [(8, 2), (8, 2), (8, 2), (3, 8), (3, 8), (3, 8)]), "1")
    assert down.k_dir == "down" and down.hits_dir == "up"                     # K's fell, hits rose


def test_batter_trend_dots_windows_streak():
    # 12 games, hit in the last 4 straight, 9 of last 10
    games = [1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1]
    t = T.batter_trend(_batter_pa("5", games), "5", "High conviction", "neutral",
                       "1+ Hit · Score 95", ["Reaching base"], ["Small sample"])
    assert t.dots == tuple(games)
    assert dict(t.windows)["L5"] == "5 / 5" and dict(t.windows)["L10"] == "9 / 10"
    assert t.hit_streak == 6                                                  # trailing 1s
    assert t.category == "High conviction"


def test_batter_trend_requires_games():
    assert T.batter_trend(_batter_pa("5", [1, 0, 1]), "5", "x", "up", "l", [], []) is None  # 3 < MIN_GAMES


def test_render_pitcher_and_batter_trends():
    pt = T.pitcher_trend(_pitcher_pa("1", [(6, 4), (7, 5), (5, 3), (6, 4), (8, 2)]), "1")
    bt = T.batter_trend(_batter_pa("5", [1, 0, 1, 1, 1, 0, 1, 1]), "5", "Heating up", "up",
                        "1+ Hit · Score 92", ["Hot"], [])
    ph = C.pitcher_trends_html((pt,))
    bh = C.batter_trends_html((bt,))
    assert "Pitcher Trends" in ph and "mlb-spark" in ph and "Strikeouts" in ph
    assert ph.count("<div") == ph.count("</div>")
    assert "Player Trends" in bh and "mlb-dot-row" in bh and "HEATING UP" in bh.upper() or "Heating up" in bh
    assert bh.count("<div") == bh.count("</div>")


def test_empty_trends_render_nothing():
    assert C.pitcher_trends_html(()) == "" and C.batter_trends_html(()) == ""
