"""The editorial feedback loop — did the games we called interesting play out that way?

The engine had no feedback of any kind: props are graded nightly, a game's interest
score never was, so accumulating slates taught it nothing. These guard the recording
layer and, above all, the leak fix that makes a backfill honest.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from domain.models import SlateGame
from services import game_outcomes as go


def _final(away_score, home_score, winner, away_rec="70-47", home_rec="66-51"):
    from datetime import datetime
    return SlateGame(league="MLB", game_id="g1", start_time=datetime(2026, 8, 9, 19, 0),
                     away_short="AAA", home_short="HHH", state="final",
                     away_score=away_score, home_score=home_score, winner=winner,
                     away_record=away_rec, home_record=home_rec)


# --- the leak ---------------------------------------------------------------------

def test_a_completed_games_record_is_rewound_to_first_pitch():
    """ESPN's record for a finished game already counts it — the Yankees show 66-51
    on a day they won and 66-52 the next. Scoring a past slate from that feeds the
    result into the input, always crediting the winner."""
    assert go.pregame_record("66-51", won=True) == "65-51"
    assert go.pregame_record("66-51", won=False) == "66-50"


def test_rewinding_handles_ties_and_leaves_odd_input_alone():
    assert go.pregame_record("9-0-1", won=True) == "8-0-1"
    assert go.pregame_record("TBD", won=True) == "TBD"
    assert go.pregame_record(None, won=True) is None
    assert go.pregame_record("0-5", won=True) == "0-5"      # never goes negative


def test_an_unfinished_game_is_left_untouched():
    """Nothing to undo before the game has been played."""
    g = SlateGame(league="MLB", game_id="g", state="pre", away_record="10-5", home_record="7-8")
    assert go.as_pregame(g).away_record == "10-5"


def test_as_pregame_rewinds_only_the_relevant_side():
    g = go.as_pregame(_final(5, 2, "away", away_rec="70-47", home_rec="66-51"))
    assert g.away_record == "69-47", "the winner loses the win"
    assert g.home_record == "66-50", "the loser loses the loss"


# --- recording ---------------------------------------------------------------------

def test_only_finished_games_are_gradeable():
    live = SlateGame(league="MLB", game_id="g", state="live", away_score=1, home_score=0)
    assert go.outcome_for(live, 60, ["even"]) is None
    assert go.outcome_for(_final(5, 2, "away"), 60, ["even"]) is not None


def test_outcome_captures_margin_total_and_signals():
    o = go.outcome_for(_final(7, 2, "away"), 66, ["solid", "even"])
    assert (o.margin, o.total, o.winner) == (5, 9, "away")
    assert o.signals == "even,solid"          # sorted, so segments group cleanly later


def test_recording_is_idempotent_per_game():
    fd, path = tempfile.mkstemp(suffix=".db"); Path(path).unlink()
    o = go.outcome_for(_final(5, 2, "away"), 60, ["even"])
    assert go.record([o], db_path=path) == 1
    go.record([o], db_path=path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM game_outcomes").fetchone()[0] == 1
    Path(path).unlink()


def test_no_database_yields_no_rows_rather_than_an_error():
    assert go.load(db_path="/nonexistent/nope.db") == []


# --- calibration --------------------------------------------------------------------

def _rows(pairs, league="MLB"):
    return [{"league": league, "interest_score": s, "margin": m} for s, m in pairs]


def test_calibration_withholds_a_verdict_on_a_thin_sample():
    """Below the minimum it returns nothing rather than a number nobody should read."""
    assert go.calibration(_rows([(70, 1), (30, 9)])) == {}


def test_calibration_compares_high_against_low_interest():
    rows = _rows([(70, 1)] * 8 + [(30, 9)] * 8)
    c = go.calibration(rows, "MLB")
    assert c["high"]["mean_margin"] < c["low"]["mean_margin"]
    assert c["high"]["close_rate"] > c["low"]["close_rate"]


def test_calibration_is_reported_within_a_league():
    """A six-point basketball margin and a six-run baseball margin are not the same
    thing; pooling them measured -0.017 where MLB alone measured -0.111."""
    rows = _rows([(70, 1)] * 8 + [(30, 9)] * 8) + _rows([(70, 20)] * 8, league="WNBA")
    assert go.calibration(rows, "MLB")["n"] == 16
    assert go.calibration(rows, "WNBA") == {}          # too few to judge
