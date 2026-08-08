"""Offline tests for the batter strikeout + walk scorers, their registry entries,
grading, and pill classification (batter Ks must not collide with SP strikeouts)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd

from domain import markets
from services import grading, snapshots
from src.batter_kbb_opportunity import score_bb_opportunities, score_k_opportunities


def _pa(bid, team, per_game):
    """One PA row per (game, event) carrying is_strikeout / is_walk flags. per_game is
    a list of (k, bb) tuples — expand to that many flagged PAs per game."""
    rows = []
    for gi, (k, bb) in enumerate(per_game):
        for _ in range(max(1, k + bb)):
            rows.append({"batting_team": team, "batter_id": bid, "batter_name": f"Bat {bid}",
                         "game_date": f"2026-06-{gi + 1:02d}", "game_id": gi,
                         "is_strikeout": 1 if k > 0 else 0, "is_walk": 1 if bb > 0 else 0})
            k = max(0, k - 1); bb = max(0, bb - 1)
    return pd.DataFrame(rows)


def test_k_over_only_high_whiff_batter():
    # 2 K nearly every game → reliable 2+ over.
    pa = _pa(1, "T", [(2, 0)] * 8 + [(1, 0), (3, 0)])
    r = score_k_opportunities(pa, ["T"])
    assert not r.empty
    row = r.iloc[0]
    assert row.market_key == "batter_k" and row.direction == "over" and row.threshold == 2


def test_k_skips_low_strikeout_batter():
    # Rarely 2+ K → not a distinctive over → skipped (1+ K is never offered).
    pa = _pa(1, "T", [(1, 0), (0, 0)] * 5)
    assert score_k_opportunities(pa, ["T"]).empty


def test_bb_over_for_patient_hitter():
    pa = _pa(1, "T", [(0, 1)] * 8 + [(0, 2), (0, 0)])
    r = score_bb_opportunities(pa, ["T"])
    assert not r.empty
    assert r.iloc[0].market_key == "batter_bb" and r.iloc[0].direction == "over"


def test_registry_labels_and_grading():
    assert markets.format_market("batter_k", 2, "over") == "2+ Strikeouts"
    assert markets.format_market("batter_bb", 1, "over") == "1+ Walks"
    assert markets.grade("batter_k", 2, 2, "over") == "hit"
    assert markets.grade("batter_k", 1, 2, "over") == "miss"
    assert markets.recommendation_label("batter_k", 2, "over") == "Over 1.5"


def test_pill_classification_prefers_market_key():
    # Batter Ks and SP Ks both read "Strikeouts"; the stored key disambiguates.
    assert markets.prop_type_for("batter_k") == "batter_k"
    assert markets.prop_type_for("sp_k") == "sp_k"
    # A batter-K row (market text "2+ Strikeouts") must classify as batter_k, not sp_k.
    assert markets.prop_type_for("batter_k", "MLB", "2+ Strikeouts") == "batter_k"


def _snap(conn, pid, market, key, threshold, score):
    conn.execute(
        """INSERT INTO opportunity_snapshots
        (snapshot_date, captured_on, calculated_at, league, player_id, player_name,
         team_name, market, market_key, direction, threshold, opportunity_score, stability_score)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("2026-06-01", "2026-06-02", "2026-06-01T12:00", "MLB", pid, f"P{pid}", "T",
         market, key, "over", threshold, score, 70))


def test_grading_batter_k_and_bb(tmp_path):
    db = tmp_path / "kbb.db"
    with sqlite3.connect(db) as conn:
        snapshots.ensure_table(conn)
        conn.execute("""CREATE TABLE plate_appearances (batter_id TEXT, game_date TEXT,
            is_strikeout INTEGER, is_walk INTEGER, is_hit INTEGER, total_bases INTEGER)""")
        _snap(conn, "1", "2+ Strikeouts", "batter_k", 2, 80)   # 2 K → hit
        _snap(conn, "2", "2+ Strikeouts", "batter_k", 2, 80)   # 1 K → miss
        _snap(conn, "3", "1+ Walks", "batter_bb", 1, 80)       # 1 BB → hit
        _snap(conn, "4", "2+ Strikeouts", "batter_k", 2, 80)   # did not bat → void
        conn.executemany(
            "INSERT INTO plate_appearances VALUES (?,?,?,?,?,?)",
            [("1", "2026-06-01", 1, 0, 0, 0), ("1", "2026-06-01", 1, 0, 0, 0),
             ("2", "2026-06-01", 1, 0, 0, 0),
             ("3", "2026-06-01", 0, 1, 0, 0)])
        conn.commit()
    grading.grade_slate(date(2026, 6, 1), db_path=db)
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        res = {r["player_id"]: (r["result"], r["actual_value"])
               for r in conn.execute("SELECT player_id, result, actual_value FROM opportunity_snapshots")}
    assert res["1"] == ("hit", 2.0)
    assert res["2"] == ("miss", 1.0)
    assert res["3"] == ("hit", 1.0)
    assert res["4"] == ("void", None)
