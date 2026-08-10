"""What each market has actually converted.

An Opportunity Score is comparable only within its market — on the same 50-69 band,
total bases has converted 21.4% and SP hits allowed 60.0%. These guard the caveat that
says so, and in particular guard it against firing on a market whose record merely
*looks* bad on a handful of rows.
"""

from __future__ import annotations

import sqlite3

from services.calibration import (
    MIN_GRADED, MarketRecord, annotate, market_records, poor_market_note,
)


def _record(hits, misses, key="m"):
    return MarketRecord(key, hits, misses)


def test_a_poor_market_with_a_real_sample_is_flagged():
    rec = _record(200, 800)                 # 20% over 1,000
    assert rec.usable and rec.is_poor
    assert "20%" in rec.note and "1,000" in rec.note


def test_a_poor_looking_market_on_a_thin_sample_is_not_flagged():
    """batter_bb sits at 19% on 21 graded rows. That is not yet a track record, and
    saying so would condemn a market on noise."""
    rec = _record(4, 17)
    assert not rec.usable and not rec.is_poor
    assert rec.graded < MIN_GRADED


def test_a_healthy_market_says_nothing():
    assert not _record(570, 430).is_poor    # 57%, no comment needed


def test_the_note_is_observed_history_not_a_forecast():
    """R4 rules out 'expected hit rate' wording — this is what happened, with its
    sample size, and the reader draws the conclusion."""
    note = _record(200, 800).note
    assert "expected" not in note.lower() and "converted" in note
    assert "graded picks" in note


def test_no_claim_without_a_database():
    assert market_records(db_path="/nonexistent/nope.db") == {}
    assert poor_market_note("batter_tb", {}) is None
    assert poor_market_note(None) is None


class _Opp:
    def __init__(self, market_key):
        self.market_key = market_key
        self.negative_evidence = []


def test_annotate_touches_only_the_poor_markets():
    recs = {"bad": _record(200, 800, "bad"), "good": _record(570, 430, "good")}
    bad, good = _Opp("bad"), _Opp("good")
    annotate([bad, good], recs)
    assert bad.negative_evidence and "20%" in bad.negative_evidence[0]
    assert good.negative_evidence == []


def test_annotate_does_not_duplicate_on_a_second_pass():
    recs = {"bad": _record(200, 800, "bad")}
    o = _Opp("bad")
    annotate([o], recs); annotate([o], recs)
    assert len(o.negative_evidence) == 1


def test_reads_the_real_ledger_shape():
    """Smoke test against the actual table definition, not a fixture."""
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE opportunity_snapshots (market_key TEXT, result TEXT)")
        conn.executemany("INSERT INTO opportunity_snapshots VALUES (?,?)",
                         [("batter_tb", "miss")] * 90 + [("batter_tb", "hit")] * 20)
    recs = market_records(db_path=path)
    os.unlink(path)
    assert recs["batter_tb"].graded == 110 and recs["batter_tb"].is_poor
