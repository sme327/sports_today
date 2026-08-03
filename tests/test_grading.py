"""Offline tests for prop grading, reads, and the results feed.

Builds a self-contained temp DB with minimal snapshot + plate-appearance +
WNBA-log tables and grades against them — covering hit / miss / void (incl. the
DNP honesty rule), idempotency, the no-grading-today guard, dedup/min-score
reads, the summary (voids excluded from hit rate), and the row renderer.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from components.results_feed import _actual_display, result_summary_html, results_feed_html
from services import grading, snapshots

SLATE = "2026-06-01"


def _snap(conn, pid, league, market, threshold, score):
    conn.execute(
        f"""INSERT INTO opportunity_snapshots
        (snapshot_date, captured_on, calculated_at, league, player_id, player_name,
         team_name, market, threshold, opportunity_score, stability_score)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (SLATE, "2026-06-02", "2026-06-01T12:00:00", league, pid, f"Player {pid}",
         "Team", market, threshold, score, 70))


def _seed(tmp_path):
    db = tmp_path / "grade.db"
    with sqlite3.connect(db) as conn:
        snapshots.ensure_table(conn)
        conn.executescript(
            """CREATE TABLE plate_appearances (batter_id TEXT, game_date TEXT, is_hit INTEGER);
               CREATE TABLE wnba_player_game_logs (player_id TEXT, game_date TEXT,
                   points REAL, rebounds REAL, assists REAL, minutes REAL);""")
        # MLB: A got 1 hit (hit), B 0 hits (miss), C did not bat (void)
        _snap(conn, "1", "MLB", "1+ Hit", 1, 90)
        _snap(conn, "2", "MLB", "1+ Hit", 1, 88)
        _snap(conn, "3", "MLB", "1+ Hit", 1, 60)
        conn.executemany("INSERT INTO plate_appearances VALUES (?,?,?)",
                         [("1", SLATE, 1), ("1", SLATE, 0), ("2", SLATE, 0), ("2", SLATE, 0)])
        # WNBA: D 18 pts (hit≥15), E 10 pts (miss), F no log (void), G DNP 0 min (void)
        _snap(conn, "10", "WNBA", "15+ Points", 15, 91)
        _snap(conn, "11", "WNBA", "15+ Points", 15, 80)
        _snap(conn, "12", "WNBA", "15+ Points", 15, 77)
        _snap(conn, "13", "WNBA", "6+ Rebounds", 6, 79)
        conn.executemany("INSERT INTO wnba_player_game_logs VALUES (?,?,?,?,?,?)",
                         [("10", SLATE, 18, 5, 3, 30), ("11", SLATE, 10, 4, 2, 28),
                          ("13", SLATE, 0, 0, 0, 0)])
        conn.commit()
    return db


def _result(db, pid):
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        r = conn.execute("SELECT result, actual_value FROM opportunity_snapshots WHERE player_id=?",
                         (pid,)).fetchone()
    return (r["result"], r["actual_value"])


def test_grading_hit_miss_void(tmp_path):
    db = _seed(tmp_path)
    summary = grading.grade_slate(date(2026, 6, 1), db_path=db)
    assert summary["graded"] == 7
    assert _result(db, "1") == ("hit", 1.0)     # MLB 1 hit
    assert _result(db, "2") == ("miss", 0.0)    # MLB 0 hits
    assert _result(db, "3") == ("void", None)   # MLB did not bat
    assert _result(db, "10") == ("hit", 18.0)   # WNBA 18 ≥ 15
    assert _result(db, "11") == ("miss", 10.0)  # WNBA 10 < 15
    assert _result(db, "12") == ("void", None)  # WNBA no log
    assert _result(db, "13") == ("void", None)  # WNBA DNP (0 minutes) → void, not miss


def test_grading_idempotent_and_force(tmp_path):
    db = _seed(tmp_path)
    grading.grade_slate(date(2026, 6, 1), db_path=db)
    again = grading.grade_slate(date(2026, 6, 1), db_path=db)     # nothing pending
    assert again["graded"] == 0
    forced = grading.grade_slate(date(2026, 6, 1), db_path=db, force=True)
    assert forced["graded"] == 7


def test_no_grading_today_or_future(tmp_path):
    db = _seed(tmp_path)
    assert grading.grade_slate(date.today(), db_path=db)["graded"] == 0
    assert grading.grade_slate(date.today() + timedelta(days=1), db_path=db)["graded"] == 0


def test_reads_and_summary(tmp_path):
    db = _seed(tmp_path)
    grading.grade_slate(date(2026, 6, 1), db_path=db)
    served = grading.load_graded_slate(date(2026, 6, 1), min_score=80, db_path=db)
    assert {r["player_id"] for r in served} == {"1", "2", "10", "11"}   # score ≥ 80
    assert served[0]["opportunity_score"] >= served[-1]["opportunity_score"]  # sorted desc
    s = grading.summarize(served)
    assert s["overall"]["hit"] == 2 and s["overall"]["miss"] == 2 and s["overall"]["void"] == 0
    assert s["overall"]["hit_rate"] == 0.5
    # per-league split
    assert set(s["by_league"]) == {"MLB", "WNBA"}


def test_summary_excludes_void_from_rate(tmp_path):
    db = _seed(tmp_path)
    grading.grade_slate(date(2026, 6, 1), db_path=db)
    allrows = grading.load_graded_slate(date(2026, 6, 1), db_path=db)
    s = grading.summarize(allrows)["overall"]
    assert s["void"] == 3
    # hit_rate = hits / (hits+miss) = 2/4, voids not in the denominator
    assert s["hit"] == 2 and s["miss"] == 2 and s["hit_rate"] == 0.5


# --------------------------------------------------- results feed rendering ---
def test_actual_display_phrasing():
    assert _actual_display({"result": "hit", "actual_value": 1, "market": "1+ Hit"}) == "1 hit"
    assert _actual_display({"result": "hit", "actual_value": 2, "market": "1+ Hit"}) == "2 hits"
    assert _actual_display({"result": "hit", "actual_value": 18, "market": "15+ Points"}) == "18 pts"
    assert _actual_display({"result": "void"}) == "did not play"


def test_results_feed_and_summary_html():
    rows = [
        {"result": "hit", "actual_value": 2, "market": "1+ Hit", "player_name": "A",
         "team_name": "T", "opportunity_score": 90},
        {"result": "miss", "actual_value": 0, "market": "1+ Hit", "player_name": "B",
         "team_name": "T", "opportunity_score": 88},
        {"result": "void", "actual_value": None, "market": "1+ Hit", "player_name": "C",
         "team_name": "T", "opportunity_score": 60},
    ]
    html = results_feed_html(rows)
    assert html.count('class="result-row') == 3
    assert "result-mark hit" in html and "result-mark miss" in html and "result-mark void" in html
    assert "did not play" in html and "2 hits" in html
    summ = grading.summarize(rows)["overall"]
    chip = result_summary_html(summ, "MLB")
    assert "50% hit" in chip and "1 hit" in chip and "1 miss" in chip and "1 void" in chip


def test_results_feed_empty():
    assert "No graded props" in results_feed_html([])


# ----------------------------------------------------- SP pitcher props -------
def _seed_sp(tmp_path):
    """A DB where two pitchers started: P1 got 7 K / 4 hits, P2 got 3 K / 8 hits."""
    db = tmp_path / "sp.db"
    with sqlite3.connect(db) as conn:
        snapshots.ensure_table(conn)
        conn.execute("""CREATE TABLE plate_appearances
            (pitcher_id TEXT, game_date TEXT, inning TEXT, is_strikeout INTEGER, is_hit INTEGER)""")
        pas = []
        for i in range(7):   # P1: 7 K
            pas.append(("1", SLATE, "1T" if i == 0 else "3T", 1, 0))
        for i in range(4):   # P1: 4 hits
            pas.append(("1", SLATE, "4T", 0, 1))
        for i in range(3):   # P2: 3 K
            pas.append(("2", SLATE, "1T" if i == 0 else "5T", 1, 0))
        for i in range(8):   # P2: 8 hits
            pas.append(("2", SLATE, "6T", 0, 1))
        # P3 pitched but never in the 1st inning → not a starter
        pas += [("3", SLATE, "7T", 1, 0), ("3", SLATE, "8T", 0, 1)]
        conn.executemany("INSERT INTO plate_appearances VALUES (?,?,?,?,?)", pas)
        _snap(conn, "1", "MLB", "5+ Strikeouts (SP)", 5, 80)
        _snap(conn, "1", "MLB", "≤ 5 Hits Allowed (SP)", 5, 78)
        _snap(conn, "2", "MLB", "5+ Strikeouts (SP)", 5, 70)
        _snap(conn, "2", "MLB", "≤ 5 Hits Allowed (SP)", 5, 72)
        _snap(conn, "3", "MLB", "5+ Strikeouts (SP)", 5, 60)   # non-starter → void
        conn.commit()
    return db


def test_grade_sp_strikeouts_and_hits_allowed(tmp_path):
    db = _seed_sp(tmp_path)
    grading.grade_slate(date(2026, 6, 1), db_path=db)
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = {(r["player_id"], r["market"]): (r["result"], r["actual_value"])
                for r in conn.execute("SELECT player_id, market, result, actual_value "
                                      "FROM opportunity_snapshots")}
    assert rows[("1", "5+ Strikeouts (SP)")] == ("hit", 7.0)       # 7 ≥ 5
    assert rows[("1", "≤ 5 Hits Allowed (SP)")] == ("hit", 4.0)    # 4 ≤ 5 (under)
    assert rows[("2", "5+ Strikeouts (SP)")] == ("miss", 3.0)      # 3 < 5
    assert rows[("2", "≤ 5 Hits Allowed (SP)")] == ("miss", 8.0)   # 8 > 5 (under fails)
    assert rows[("3", "5+ Strikeouts (SP)")] == ("void", None)     # did not start


def test_actual_display_sp_markets():
    assert _actual_display({"result": "hit", "actual_value": 7, "market": "5+ Strikeouts (SP)"}) == "7 K"
    assert _actual_display({"result": "miss", "actual_value": 8,
                            "market": "≤ 5 Hits Allowed (SP)"}) == "8 hits allowed"


def test_prop_type_classification():
    from components.prop_filters import prop_type_of
    from domain.models import Opportunity

    def opp(league, market):
        return Opportunity(league=league, player_id="1", player_name="X", team_id=None,
                           team_name="T", market=market, threshold=1,
                           opportunity_score=50, stability_score=50)
    assert prop_type_of(opp("MLB", "1+ Hit")) == "hits"
    assert prop_type_of(opp("MLB", "6+ Strikeouts (SP)")) == "sp_k"
    assert prop_type_of(opp("MLB", "≤ 5 Hits Allowed (SP)")) == "sp_hits"
    assert prop_type_of(opp("WNBA", "15+ Points")) == "points"
    assert prop_type_of(opp("WNBA", "6+ Rebounds")) == "rebounds"
    assert prop_type_of(opp("WNBA", "3+ Assists")) == "assists"
