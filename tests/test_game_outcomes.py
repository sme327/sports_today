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


# --- The market line, recorded for measurement and consumed by nothing ----------------

def _cache_row(conn, slate, league, fetched_at, games):
    import json
    conn.execute("CREATE TABLE IF NOT EXISTS schedule_cache (league TEXT, slate_date TEXT, "
                 "fetched_at TEXT, source TEXT, status TEXT, game_count INTEGER, payload TEXT)")
    conn.execute("INSERT INTO schedule_cache VALUES (?,?,?,?,?,?,?)",
                 (league, slate, fetched_at, "espn", "ok", len(games), json.dumps(games)))


def _game(gid, state="pre", total=52.5, spread=-6.5):
    line = {"detail": "X -6.5", "spread": spread, "total": total,
            "favourite": "X", "provider": "Draft Kings"}
    return {"game_id": gid, "state": state, "meta": {"market_line": line}}


def test_a_line_is_recovered_from_before_kickoff(tmp_path):
    """ESPN drops odds once a game starts, so by grade time there is nothing to read.

    Later fetches on the same day legitimately carry fewer lines — the early games have
    already kicked off — so a game keeps the newest line *any* fetch saw rather than the
    newest fetch's answer.
    """
    import sqlite3

    from services import game_outcomes as go

    db = tmp_path / "t.db"
    with sqlite3.connect(db) as conn:
        _cache_row(conn, "2026-09-05", "NCAAF", "2026-09-04T08:00", [
            _game("A", total=51.5), _game("B", total=60.5)])
        _cache_row(conn, "2026-09-05", "NCAAF", "2026-09-05T10:00", [
            _game("A", total=52.5),                       # line moved; keep this one
            {"game_id": "B", "state": "in", "meta": {}}])  # already live, odds gone
        conn.commit()

    lines = go.pregame_lines("2026-09-05", "NCAAF", db_path=db)
    assert lines["A"]["total"] == 52.5
    assert lines["A"]["captured_at"] == "2026-09-05T10:00"
    # B's absent odds are a fact about ESPN's board, not the market — keep the earlier one.
    assert lines["B"]["total"] == 60.5
    assert lines["B"]["captured_at"] == "2026-09-04T08:00"


def test_a_rerun_never_erases_a_line_already_recorded(tmp_path):
    """The recorded line is the one captured closest to kickoff. Re-running the recorder
    after the game reads an empty board, and must leave what is stored alone."""
    from services import game_outcomes as go

    db = tmp_path / "t.db"
    base = dict(slate_date="2026-09-05", league="NCAAF", game_id="A", away="X", home="Y",
                interest_score=0, signals="", margin=7, total=59, winner="home")
    go.record([go.GameOutcome(**base, market_total=52.5, market_spread=-6.5,
                              market_book="Draft Kings", line_captured_at="2026-09-05T10:00")],
              db_path=db)
    go.record([go.GameOutcome(**base)], db_path=db)      # the post-game re-run

    row = go.load(db_path=db)[0]
    assert row["market_total"] == 52.5
    assert row["market_book"] == "Draft Kings"


def test_totals_record_separates_pushes_from_sides(tmp_path):
    from services import game_outcomes as go

    rows = [
        {"league": "NCAAF", "total": 59, "market_total": 52.5},   # over
        {"league": "NCAAF", "total": 48, "market_total": 56.5},   # under
        {"league": "NCAAF", "total": 52, "market_total": 52.0},   # push
        {"league": "NCAAF", "total": 41, "market_total": None},   # no line captured
        {"league": "MLB", "total": 9, "market_total": 8.5},       # another league
    ]
    r = go.totals_record(rows, "NCAAF")
    assert (r["n"], r["over"], r["under"], r["push"]) == (3, 1, 1, 1)
    assert r["over_rate"] == 50.0          # pushes excluded from the rate
    assert go.totals_record(rows, "MLB")["n"] == 1


def test_the_recorded_line_reaches_no_scorer():
    """Odds may be displayed and recorded; they may never be consumed.

    `editorial` has its own AST and behavioural guards. This is the second door: the
    columns now sit in a table the calibration reads, so no scoring or editorial module
    may reference them by name.
    """
    from pathlib import Path

    market_columns = ("market_total", "market_spread", "market_favourite", "market_book")
    for path in [Path("services/editorial.py"), Path("services/ncaaf_context.py"),
                 *Path("src").glob("*scorer*.py"), *Path("services").glob("*_playoffs.py")]:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for column in market_columns:
            assert column not in source, f"{path} references {column}"
