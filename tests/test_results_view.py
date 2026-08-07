"""Offline tests for the R2 Daily Results components (pure HTML)."""

from __future__ import annotations

import json

from components import results_feed as F


def _tally(hit, miss, void=0, pending=0):
    dec = hit + miss
    return {"hit": hit, "miss": miss, "void": void, "pending": pending,
            "total": hit + miss + void + pending, "hit_rate": (hit / dec) if dec else None}


def test_daily_summary_record_and_not_graded():
    html = F.daily_summary_html(_tally(79, 71, void=26, pending=5), 88.4, 181)
    assert "79–71" in html and "52.7%" in html and "n=150" in html
    assert "88" in html                                   # avg score
    assert "settled props graded" in html
    # nothing decided → "Not graded", never a bare 0%
    assert "Not graded" in F.daily_summary_html(_tally(0, 0, void=3), None, 3)


def test_market_table_rows_sort_and_select():
    by_market = {"hits": _tally(66, 60), "sp_k": _tally(4, 9), "points": _tally(0, 0, void=5)}
    html = F.market_table_html(by_market, selected="hits", sort_key="sample", date_iso="2026-08-03")
    assert "Batter Hits" in html and "66–60" in html
    assert "mkt=hits" in html and "mkt-row selected" in html   # clickable + highlighted
    assert "Not graded" in html                               # points, 0 decided
    # default sort by sample → hits (126) before sp_k (13)
    assert html.index("Batter Hits") < html.index("SP Strikeouts")


def test_prop_item_disambiguates_recommendation_and_actual():
    r = {"league": "MLB", "player_name": "Freddie Freeman", "team_name": "Los Angeles Dodgers",
         "opponent": "Padres", "market": "1+ Hit", "market_key": "batter_hit",
         "direction": "over", "threshold": 1, "opportunity_score": 100, "result": "hit",
         "actual_value": 1.0, "support_evidence": json.dumps(["Reaching base often"]),
         "risk_evidence": json.dumps(["Small sample"])}
    html = F.prop_list_html([r])
    assert "Rec: Over 0.5" in html and "Actual: 1 hit" in html   # disambiguated
    assert "HIT" in html and "prop-grade r-hit" in html
    assert "Why this score?" in html and "Reaching base often" in html
    assert "<details" in html


def test_prop_void_shows_reason():
    r = {"league": "MLB", "player_name": "X", "team_name": "T", "opponent": "O",
         "market": "1+ Hit", "market_key": "batter_hit", "direction": "over", "threshold": 1,
         "opportunity_score": 90, "result": "void", "void_reason": "did not bat"}
    html = F.prop_list_html([r])
    assert "VOID" in html and "did not bat" in html
