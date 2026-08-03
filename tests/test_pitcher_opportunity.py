"""Offline tests for the starting-pitcher prop scorer (SP K's over, SP hits
allowed under). Synthetic plate appearances — no network, no DB."""

from __future__ import annotations

import pandas as pd

from src.pitcher_opportunity import (
    _choose_over, _choose_under, _per_start_lines, score_pitcher_opportunities,
)


def _pa(rows):
    return pd.DataFrame(rows, columns=["pitcher_id", "pitcher_name", "pitching_team",
                                       "game_id", "game_date", "inning", "is_strikeout", "is_hit"])


def _start(pid, gid, day, ks, hits, bf=6):
    """A start: a 1st-inning PA + filler, with `ks` strikeouts and `hits` hits."""
    rows = [(pid, "Ace", "Team", gid, day, "1T", 0, 0)]
    for i in range(bf - 1):
        rows.append((pid, "Ace", "Team", gid, day, f"{(i % 8) + 1}T",
                     1 if i < ks else 0, 1 if ks <= i < ks + hits else 0))
    # make sure exactly ks strikeouts / hits regardless of bf
    rows = [(pid, "Ace", "Team", gid, day, "1T", 0, 0)]
    for i in range(max(ks, hits, 1)):
        rows.append((pid, "Ace", "Team", gid, day, "3T", 1 if i < ks else 0, 1 if i < hits else 0))
    return rows


def test_choose_thresholds():
    assert _choose_over(6.4, (4, 5, 6, 7, 8)) == 6      # highest ≤ avg
    assert _choose_over(3.0, (4, 5, 6, 7, 8)) == 4      # fallback lowest
    assert _choose_under(5.2, (4, 5, 6, 7, 8)) == 6     # lowest ≥ avg
    assert _choose_under(9.0, (4, 5, 6, 7, 8)) == 8     # fallback highest


def test_per_start_lines_excludes_relief():
    rows = _start("1", "g1", "2026-06-01", 6, 5)
    # a relief appearance (no 1st-inning PA) must be excluded
    rows += [("1", "Ace", "Team", "g2", "2026-06-02", "6T", 1, 1),
             ("1", "Ace", "Team", "g2", "2026-06-02", "7T", 0, 1)]
    lines = _per_start_lines(_pa(rows))
    assert len(lines) == 1                              # only the real start
    assert int(lines.iloc[0]["k"]) == 6 and int(lines.iloc[0]["hits"]) == 5


def test_scorer_markets_and_thresholds():
    rows = []
    for i in range(5):                                  # 5 starts: 6 K, 5 hits each
        rows += _start("1", f"g{i}", f"2026-06-0{i+1}", 6, 5)
    scored = score_pitcher_opportunities(_pa(rows), ["1"])
    by = {r["kind"]: r for _, r in scored.iterrows()}
    assert set(by) == {"sp_k", "sp_hits"}
    assert by["sp_k"]["market"] == "6+ Strikeouts (SP)" and by["sp_k"]["threshold"] == 6
    assert by["sp_hits"]["market"] == "≤ 5 Hits Allowed (SP)" and by["sp_hits"]["threshold"] == 5
    # both cleared in all 5 starts → high recent hit rate → strong score
    assert by["sp_k"]["recent_hit_rate"] == 1.0 and by["sp_k"]["opportunity_score"] >= 70
    assert "6.0 K per start over last 5" in by["sp_k"]["support"][0]


def test_scorer_requires_minimum_starts():
    rows = _start("1", "g1", "2026-06-01", 6, 5) + _start("1", "g2", "2026-06-02", 6, 5)
    assert score_pitcher_opportunities(_pa(rows), ["1"]).empty   # only 2 starts < 3


def test_scorer_empty_inputs():
    assert score_pitcher_opportunities(pd.DataFrame(), ["1"]).empty
    assert score_pitcher_opportunities(_pa(_start("1", "g", "2026-06-01", 6, 5)), []).empty
