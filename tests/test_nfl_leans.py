"""The prop-lean ledger: record is idempotent and keeps grades, grading follows the
box score's vocabulary (hit / miss / void), and a game is only graded once final."""

from __future__ import annotations

import sqlite3

from services import nfl_leans
from services.nfl_game_notes import parse_notes
from src.espn_nfl_boxscore import parse_summary

_NOTE = b"""
game_id = "401"
away = "A"
home = "B"
kickoff = "2025-09-03"
authored = "2025-09-03"

[[leans]]
team = "A"
player = "Quincy Quarterback"
stat = "passing_yds"
line = 240.5
direction = "under"
confidence = "high"
why = "Tough pass defence."

[[leans]]
team = "A"
player = "Rex Runner"
stat = "receptions"
line = 2.5
direction = "under"
confidence = "moderate"
why = "Not a receiver."

[[leans]]
team = "B"
player = "Gone Guy"
stat = "rushing_yds"
line = 40.5
direction = "over"
confidence = "low"
why = "Scratched late, as it turned out."

[[overs]]
team = "B"
player = "Quincy Quarterback"
stat = "passing_att"
line = 30
direction = "over"
confidence = "low"
why = "A whole-number line, to test the push."

[[props]]
team = "B"
player = "Quincy Quarterback"
stat = "passing_td"
line = 1.5
direction = "pass"
why = "No edge either way."

[[props]]
team = "A"
player = "Rex Rookie"
stat = "receptions"
line = 1.5
direction = "over"
confidence = "low"
position = "rb"
why = "Not in the feed; the note names the position."
"""

_SUMMARY = {
    "header": {"competitions": [{"status": {"type": {"state": "post", "completed": True}}}]},
    "boxscore": {"players": [
        {"team": {"displayName": "A"}, "statistics": [
            {"name": "passing", "labels": ["C/ATT", "YDS", "AVG", "TD", "INT"],
             "athletes": [{"athlete": {"displayName": "Quincy Quarterback"},
                           "stats": ["19/30", "212", "7.1", "1", "0"]}]},
            {"name": "receiving", "labels": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"],
             "athletes": [{"athlete": {"displayName": "Rex Runner"},
                           "stats": ["3", "21", "7.0", "0", "9", "4"]}]},
        ]},
    ]},
}


def test_parse_summary_reduces_the_box_score_to_gradeable_stats():
    box = parse_summary(_SUMMARY)
    assert box["final"] is True and box["state"] == "post"
    q = box["players"]["Quincy Quarterback"]
    assert q["passing_comp"] == 19 and q["passing_att"] == 30 and q["passing_yds"] == 212
    assert box["players"]["Rex Runner"]["receptions"] == 3
    assert "Gone Guy" not in box["players"]
    assert parse_summary({"header": {"competitions": [{"status": {"type": {"state": "in"}}}]}})["final"] is False


def test_record_is_idempotent_and_keeps_a_grade(tmp_path):
    db = tmp_path / "l.db"
    notes = parse_notes(_NOTE)
    assert nfl_leans.record(notes, db) == 6
    assert nfl_leans.record(notes, db) == 6
    rows = nfl_leans.load(db)
    assert len(rows) == 6
    # a pass is recorded as evaluated with result "pass" from the start; the rest pend
    assert [r["result"] for r in rows if r["direction"] == "pass"] == ["pass"]
    assert all(r["result"] is None for r in rows if r["direction"] != "pass")
    assert [r["rank"] for r in rows if r["section"] == "leans"] == [1, 2, 3]
    assert [r["rank"] for r in rows if r["section"] == "overs"] == [1]
    # grade, then re-record: the grade survives, the "why" refreshes
    nfl_leans.grade_game("401", parse_summary(_SUMMARY), db)
    edited = parse_notes(_NOTE.replace(b"Tough pass defence.", b"Very tough pass defence."))
    nfl_leans.record(edited, db)
    q = next(r for r in nfl_leans.load(db) if r["stat"] == "passing_yds")
    assert q["result"] == "hit" and q["why"] == "Very tough pass defence."


def test_grading_vocabulary(tmp_path):
    db = tmp_path / "l.db"
    nfl_leans.record(parse_notes(_NOTE), db)
    # not final → untouched
    assert nfl_leans.grade_game("401", {"final": False, "players": {}}, db) == {"skipped_not_final": 1}
    assert all(r["result"] in (None, "pass") for r in nfl_leans.load(db))
    tally = nfl_leans.grade_game("401", parse_summary(_SUMMARY), db)
    assert tally == {"hit": 1, "miss": 1, "void": 3}     # Gone Guy and Rex Rookie absent, one push
    by = {(r["player"], r["stat"]): r for r in nfl_leans.load(db)}
    assert by[("Quincy Quarterback", "passing_yds")]["result"] == "hit"      # 212 < 240.5
    assert by[("Rex Runner", "receptions")]["result"] == "miss"             # 3 > 2.5
    assert by[("Gone Guy", "rushing_yds")]["result"] == "void"              # not in box score
    assert by[("Gone Guy", "rushing_yds")]["actual"] is None
    assert by[("Quincy Quarterback", "passing_att")]["result"] == "void"    # 30 == 30, push
    # a second pass changes nothing: rows already graded are not re-graded
    assert nfl_leans.grade_game("401", parse_summary(_SUMMARY), db) == {"hit": 0, "miss": 0, "void": 0}


def test_grade_due_asks_from_the_day_before_the_utc_kickoff_date(tmp_path):
    """A kickoff of 2025-09-03 is the UTC date: in the US that game is played and
    finished on the evening of the 2nd. So it is due from the 2nd, not the 1st — and
    ESPN's final flag, not the date, decides whether anything is graded."""
    from datetime import date
    db = tmp_path / "l.db"
    nfl_leans.record(parse_notes(_NOTE), db)
    calls = []
    def fetch(game_id):
        calls.append(game_id)
        return parse_summary(_SUMMARY)
    assert nfl_leans.grade_due(db, today=date(2025, 9, 1), fetch=fetch) == {}
    assert calls == []
    out = nfl_leans.grade_due(db, today=date(2025, 9, 2), fetch=fetch)
    assert calls == ["401"] and out["401"]["hit"] == 1


def test_summary_splits_and_never_prints_a_bare_zero(tmp_path):
    db = tmp_path / "l.db"
    nfl_leans.record(parse_notes(_NOTE), db)
    s = nfl_leans.summarize(nfl_leans.load(db))
    assert s["overall"]["pending"] == 5 and s["overall"]["hit_rate"] is None
    assert s["overall"]["evaluated"] == 6 and s["overall"]["called"] == 5 and s["overall"]["pass"] == 1
    assert list(s["by_section"]) == ["props", "leans", "overs"]
    assert list(s["by_confidence"]) == ["high", "moderate", "low"]
    nfl_leans.grade_game("401", parse_summary(_SUMMARY), db)
    s = nfl_leans.summarize(nfl_leans.load(db))
    assert s["overall"]["hit_rate"] == 0.5 and s["overall"]["decided"] == 2
    # volume plays cut across sections: the receptions miss and the attempts push
    # the receptions miss, the attempts push, and the rookie's receptions voided
    assert s["volume"]["miss"] == 1 and s["volume"]["void"] == 2 and s["volume"]["hit"] == 0
    assert s["by_direction"]["under"]["hit"] == 1 and s["by_stat"]["receptions"]["miss"] == 1
    assert s["games"][0]["tally"]["void"] == 3


def test_positions_come_from_the_feed_or_the_note_and_split_the_record(tmp_path):
    """The ledger never asked the note for a position: it reads the feed's most recent
    row for the player, and takes the note's word for a rookie the feed has never seen.
    The by-position and by-prop-type splits count calls only, never passes."""
    import pandas as pd
    db = tmp_path / "l.db"
    with sqlite3.connect(db) as conn:
        pd.DataFrame([
            {"game_date": "2025-09-01", "player": "Quincy Quarterback", "position": "QB"},
            {"game_date": "2025-09-01", "player": "Rex Runner", "position": "WR"},
            {"game_date": "2025-09-08", "player": "Rex Runner", "position": "RB"},   # latest wins
        ]).to_sql("nfl_player_games", conn, index=False)
    nfl_leans.record(parse_notes(_NOTE), db)
    pos = {(r["player"], r["stat"]): r["position"] for r in nfl_leans.load(db)}
    assert pos[("Quincy Quarterback", "passing_yds")] == "QB"
    assert pos[("Rex Runner", "receptions")] == "RB"
    assert pos[("Rex Rookie", "receptions")] == "RB"          # from the note
    assert pos[("Gone Guy", "rushing_yds")] == ""             # nobody knows
    nfl_leans.grade_game("401", parse_summary(_SUMMARY), db)
    s = nfl_leans.summarize(nfl_leans.load(db))
    assert "pass" not in {r for t in s["by_stat"].values() for r in [t["pass"]] if r}
    assert s["by_position"]["QB"]["hit"] == 1                  # passing yards hit
    assert s["by_position"]["RB"]["miss"] == 1                 # Rex Runner's receptions
    assert "unknown" in s["by_position"]                       # Gone Guy
    assert list(s["by_stat"])[0] in ("passing yards", "receptions")   # most decided first
    assert all(t["pass"] == 0 for t in s["by_stat"].values())


def test_an_older_ledger_gains_the_position_column(tmp_path):
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE nfl_lean_ledger (game_id TEXT, kickoff TEXT, away TEXT, home TEXT, "
                     "team TEXT, player TEXT, stat TEXT, line REAL, direction TEXT, section TEXT, "
                     "rank INTEGER, confidence TEXT, why TEXT, authored TEXT, fingerprint TEXT, "
                     "recorded_at TEXT, actual REAL, result TEXT, graded_at TEXT, "
                     "PRIMARY KEY (game_id, player, stat, line, direction))")
        conn.execute("INSERT INTO nfl_lean_ledger VALUES ('g','2025-09-03','A','B','A','P','receptions',"
                     "2.5,'under','leans',1,'high','w','2025-09-03','f','t',NULL,NULL,NULL)")
    rows = nfl_leans.load(db)
    assert rows[0]["position"] == "" and len(rows) == 1


def test_missing_table_and_empty_db_are_not_crashes(tmp_path):
    assert nfl_leans.load(tmp_path / "nope.db") == []
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    assert nfl_leans.load(db) == [] and nfl_leans.games_due(db) == []


def test_a_failed_fetch_is_reported_per_game_and_does_not_stop_the_rest(tmp_path):
    from datetime import date
    db = tmp_path / "l.db"
    nfl_leans.record(parse_notes(_NOTE), db)
    def fetch(game_id):
        raise RuntimeError("403 Forbidden")
    out = nfl_leans.grade_due(db, today=date(2025, 9, 3), fetch=fetch)
    assert out == {"401": {"error": "RuntimeError: 403 Forbidden"}}
    assert all(r["result"] in (None, "pass") for r in nfl_leans.load(db))


def test_the_box_score_client_sends_no_browser_user_agent():
    """ESPN's summary endpoint answered 403 to browser-shaped agents and 200 to the
    requests default on 2026-09-09; the first grading run died on it."""
    from src import espn_nfl_boxscore as m
    assert "User-Agent" not in m._HEADERS
