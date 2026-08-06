"""Offline tests for the Results score-band ranges (minimums + exact 99/100)."""

from __future__ import annotations

from views import results as R


def test_band_ranges():
    assert R._BAND_RANGE["all"] == (0.0, 100.0)
    assert R._BAND_RANGE["95"] == (95.0, 100.0)
    assert R._BAND_RANGE["99"] == (99.0, 99.0)     # exact
    assert R._BAND_RANGE["100"] == (100.0, 100.0)  # exact


def test_band_labels():
    assert R._band_label(0.0, 100.0) == "all scores"
    assert R._band_label(90.0, 100.0) == "scored ≥ 90"
    assert R._band_label(100.0, 100.0) == "scored exactly 100"
    assert R._band_label(99.0, 99.0) == "scored exactly 99"


def test_exact_band_filters_to_that_score():
    rows = [{"opportunity_score": s, "result": "hit"} for s in (98, 99, 99, 100, 100, 100)]
    lo, hi = R._BAND_RANGE["100"]
    assert len([r for r in rows if lo <= r["opportunity_score"] <= hi]) == 3
    lo, hi = R._BAND_RANGE["99"]
    assert len([r for r in rows if lo <= r["opportunity_score"] <= hi]) == 2
