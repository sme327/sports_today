"""Offline tests for the starting-pitcher prop scorer (SP K's over, SP hits
allowed under). Synthetic plate appearances — no network, no DB."""

from __future__ import annotations

import pandas as pd

from src.pitcher_opportunity import _best_direction, _per_start_lines, score_pitcher_opportunities


def _pa(rows):
    return pd.DataFrame(rows, columns=["pitcher_id", "pitcher_name", "pitching_team",
                                       "game_id", "game_date", "inning", "is_strikeout", "is_hit"])


def _start(pid, gid, day, ks, hits, bf=20):
    """A realistic start: a 1st-inning PA + `bf`-1 more, with `ks` strikeouts and
    `hits` hits (disjoint), the rest outs. bf ≥ MIN_START_BF so it counts."""
    rows = [(pid, "Ace", "Team", gid, day, "1T", 0, 0)]
    for i in range(bf - 1):
        rows.append((pid, "Ace", "Team", gid, day, "3T",
                     1 if i < ks else 0, 1 if ks <= i < ks + hits else 0))
    return rows


def test_best_direction_avoids_trivial_extremes():
    import pandas as pd
    g = (4, 5, 6, 7, 8)
    # dominant K pitcher → a meaningful over (7+), not the trivial "≤ 8"
    d = _best_direction(pd.Series([7, 8, 6, 7, 8]), g)
    assert d["direction"] == "over" and 6 <= d["threshold"] <= 7
    # stingy hits pitcher → a meaningful under (≤ low), not the trivial "4+"
    d = _best_direction(pd.Series([2, 3, 1, 3, 2]), g)
    assert d["direction"] == "under" and d["threshold"] <= 5
    # vulnerable hits pitcher → a meaningful over
    d = _best_direction(pd.Series([8, 7, 9, 6, 8]), g)
    assert d["direction"] == "over" and d["threshold"] >= 6


def test_per_start_lines_excludes_relief():
    rows = _start("1", "g1", "2026-06-01", 6, 5)
    # a relief appearance (no 1st-inning PA) must be excluded
    rows += [("1", "Ace", "Team", "g2", "2026-06-02", "6T", 1, 1),
             ("1", "Ace", "Team", "g2", "2026-06-02", "7T", 0, 1)]
    lines = _per_start_lines(_pa(rows))
    assert len(lines) == 1                              # only the real start
    assert int(lines.iloc[0]["k"]) == 6 and int(lines.iloc[0]["hits"]) == 5


def test_scorer_high_k_low_hits_gives_k_over_and_hits_under():
    # a dominant starter: many K's, few hits → K over + hits under
    ks, hits = [7, 8, 6, 7, 8], [2, 3, 1, 3, 2]
    rows = []
    for i, (k, h) in enumerate(zip(ks, hits)):
        rows += _start("1", f"g{i}", f"2026-06-0{i+1}", k, h)
    by = {r["kind"]: r for _, r in score_pitcher_opportunities(_pa(rows), ["1"]).iterrows()}
    assert by["sp_k"]["market"].endswith("Strikeouts (SP)") and "+" in by["sp_k"]["market"]  # over
    assert by["sp_hits"]["market"].startswith("≤")                                            # under
    assert "K per start over last 5" in by["sp_k"]["support"][0]


def test_scorer_serves_hits_over_for_vulnerable_starter():
    # a starter who gets tagged: high hits every start → hits-allowed OVER, not under
    rows = []
    for i, h in enumerate([8, 7, 9, 6, 8]):
        rows += _start("1", f"g{i}", f"2026-06-0{i+1}", 3, h)
    by = {r["kind"]: r for _, r in score_pitcher_opportunities(_pa(rows), ["1"]).iterrows()}
    market = by["sp_hits"]["market"]
    assert "Hits Allowed (SP)" in market and market[0].isdigit() and "+" in market  # OVER
    assert not market.startswith("≤")
    assert "Reached" in by["sp_hits"]["support"][1]                                  # over phrasing
    assert by["sp_hits"]["opportunity_score"] >= 70


def test_scorer_requires_minimum_starts():
    rows = _start("1", "g1", "2026-06-01", 6, 5) + _start("1", "g2", "2026-06-02", 6, 5)
    assert score_pitcher_opportunities(_pa(rows), ["1"]).empty   # only 2 starts < 3


def test_scorer_empty_inputs():
    assert score_pitcher_opportunities(pd.DataFrame(), ["1"]).empty
    assert score_pitcher_opportunities(_pa(_start("1", "g", "2026-06-01", 6, 5)), []).empty
