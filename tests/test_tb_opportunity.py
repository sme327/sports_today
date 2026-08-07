"""Offline tests for the batter Total-Bases scorer. Synthetic per-game total bases;
no DB, no network."""

from __future__ import annotations

import pandas as pd

from src.mlb_lineups import Lineups
from src.tb_opportunity import score_tb_opportunities


def _tb_pa(bid, team, per_game_tb):
    """One PA row per game carrying that game's total bases."""
    rows = [{"batting_team": team, "batter_id": bid, "batter_name": f"Bat {bid}",
             "game_date": f"2026-06-{i + 1:02d}", "game_id": i, "total_bases": tb}
            for i, tb in enumerate(per_game_tb)]
    return pd.DataFrame(rows)


def test_threshold_picks_meaningful_bar():
    # clears 2+ every game, 3+ a quarter of the time → 2+ is the stronger bet
    pa = _tb_pa(1, "Team", [2, 2, 2, 3, 2, 2, 2, 3, 2, 2, 2, 3])
    r = score_tb_opportunities(pa, ["Team"])
    row = r.iloc[0]
    assert row.market_key == "batter_tb" and row.direction == "over"
    assert row.threshold == 2
    assert "total bases per game" in row.support[0]


def test_picks_highest_reachable_bar_not_most_impressive():
    # Clears 2+ and 3+ nearly always, 4+ only ~20% → 3+ is the highest *reachable*
    # bar; the old impressiveness weighting would have chased the rarely-hit 4+.
    pa = _tb_pa(1, "Team", [3, 3, 4, 3, 2, 3, 3, 4, 3, 3])
    row = score_tb_opportunities(pa, ["Team"]).iloc[0]
    assert row.threshold == 3


def test_skips_batter_with_no_reachable_bar():
    # Rarely reaches even 2+ (clear-rate well below the floor) → no honest TB over.
    pa = _tb_pa(1, "Team", [0, 1, 0, 1, 0, 2, 0, 1, 0, 1])
    assert score_tb_opportunities(pa, ["Team"]).empty


def test_requires_minimum_games():
    pa = _tb_pa(1, "Team", [2, 3, 2, 4, 2])       # 5 < MIN_GAMES
    assert score_tb_opportunities(pa, ["Team"]).empty


def test_bench_cap_applies_via_overlay():
    pa = _tb_pa(1, "Team", [3, 3, 3, 4, 3, 3, 3, 4, 3, 3])   # strong history
    lineups = Lineups(slot={}, posted_teams=frozenset({"Team"}))  # posted, bat absent
    row = score_tb_opportunities(pa, ["Team"], lineups=lineups).iloc[0]
    assert row.risks[0] == "Not in today's posted lineup"
    assert row.opportunity_score <= 25


def test_confirmed_slot_adds_evidence():
    pa = _tb_pa(1, "Team", [2, 2, 2, 3, 2, 2, 2, 3, 2, 2])
    lineups = Lineups(slot={1: 3}, posted_teams=frozenset({"Team"}))
    row = score_tb_opportunities(pa, ["Team"], lineups=lineups).iloc[0]
    assert row.lineup_slot == 3
    assert "Batting 3rd, confirmed lineup" in row.support


def test_empty_and_missing_columns():
    assert score_tb_opportunities(pd.DataFrame(), ["Team"]).empty
    assert score_tb_opportunities(_tb_pa(1, "Team", [2] * 10), []).empty
