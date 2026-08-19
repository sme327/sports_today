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


def _snap(conn, pid, league, market, threshold, score, game_id=None):
    conn.execute(
        f"""INSERT INTO opportunity_snapshots
        (snapshot_date, captured_on, calculated_at, league, game_id, player_id, player_name,
         team_name, market, threshold, opportunity_score, stability_score)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (SLATE, "2026-06-02", "2026-06-01T12:00:00", league, game_id, pid, f"Player {pid}",
         "Team", market, threshold, score, 70))


def _seed(tmp_path):
    db = tmp_path / "grade.db"
    with sqlite3.connect(db) as conn:
        snapshots.ensure_table(conn)
        conn.executescript(
            """CREATE TABLE plate_appearances (batter_id TEXT, game_date TEXT, is_hit INTEGER);
               CREATE TABLE wnba_player_game_logs (game_id TEXT, player_id TEXT, game_date TEXT,
                   points REAL, rebounds REAL, assists REAL, minutes REAL);""")
        # MLB: A got 1 hit (hit), B 0 hits (miss), C did not bat (void)
        _snap(conn, "1", "MLB", "1+ Hit", 1, 90)
        _snap(conn, "2", "MLB", "1+ Hit", 1, 88)
        _snap(conn, "3", "MLB", "1+ Hit", 1, 60)
        conn.executemany("INSERT INTO plate_appearances VALUES (?,?,?)",
                         [("1", SLATE, 1), ("1", SLATE, 0), ("2", SLATE, 0), ("2", SLATE, 0)])
        # WNBA (matched by game_id "g1", whose box scores ARE loaded): D 18 pts (hit≥15),
        # E 10 pts (miss), F no log row (void), G DNP 0 min (void). Log game_date is a
        # UTC timestamp on the *next* day to prove the grader no longer matches on date.
        _snap(conn, "10", "WNBA", "15+ Points", 15, 91, game_id="g1")
        _snap(conn, "11", "WNBA", "15+ Points", 15, 80, game_id="g1")
        _snap(conn, "12", "WNBA", "15+ Points", 15, 77, game_id="g1")
        _snap(conn, "13", "WNBA", "6+ Rebounds", 6, 79, game_id="g1")
        conn.executemany("INSERT INTO wnba_player_game_logs VALUES (?,?,?,?,?,?,?)",
                         [("g1", "10", SLATE + "T02:00Z", 18, 5, 3, 30),
                          ("g1", "11", SLATE + "T02:00Z", 10, 4, 2, 28),
                          ("g1", "13", SLATE + "T02:00Z", 0, 0, 0, 0)])
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


def test_wnba_pending_until_its_game_is_loaded(tmp_path):
    """A WNBA prop whose game has no loaded box scores stays pending (not void),
    even though other games that day are loaded — the gate is per game_id."""
    db = tmp_path / "wp.db"
    with sqlite3.connect(db) as conn:
        snapshots.ensure_table(conn)
        conn.execute("""CREATE TABLE wnba_player_game_logs (game_id TEXT, player_id TEXT,
            game_date TEXT, points REAL, rebounds REAL, assists REAL, minutes REAL)""")
        _snap(conn, "20", "WNBA", "15+ Points", 15, 90, game_id="loaded")
        _snap(conn, "21", "WNBA", "15+ Points", 15, 90, game_id="not_loaded")
        conn.execute("INSERT INTO wnba_player_game_logs VALUES ('loaded','20',?,20,4,3,30)",
                     (SLATE + "T02:00Z",))
        conn.commit()
    grading.grade_slate(date(2026, 6, 1), db_path=db)
    assert _result(db, "20") == ("hit", 20.0)       # its game is loaded → graded
    assert _result(db, "21") == (None, None)         # its game isn't → pending, not void


def test_grading_total_bases(tmp_path):
    db = tmp_path / "tb.db"
    with sqlite3.connect(db) as conn:
        snapshots.ensure_table(conn)
        conn.execute("CREATE TABLE plate_appearances (batter_id TEXT, game_date TEXT, total_bases INTEGER)")
        _snap(conn, "1", "MLB", "2+ Total Bases", 2, 85)   # 3 TB → hit
        _snap(conn, "2", "MLB", "2+ Total Bases", 2, 80)   # 1 TB → miss
        _snap(conn, "3", "MLB", "2+ Total Bases", 2, 70)   # did not bat → void
        conn.executemany("INSERT INTO plate_appearances VALUES (?,?,?)",
                         [("1", SLATE, 2), ("1", SLATE, 1), ("2", SLATE, 1)])
        conn.commit()
    grading.grade_slate(date(2026, 6, 1), db_path=db)
    assert _result(db, "1") == ("hit", 3.0)     # 2 + 1 = 3 ≥ 2
    assert _result(db, "2") == ("miss", 1.0)    # 1 < 2
    assert _result(db, "3") == ("void", None)   # did not bat


def test_grading_waits_for_results(tmp_path):
    """A slate captured before its feed arrives must stay pending, not grade to
    all-void (which idempotency would then freeze)."""
    db = tmp_path / "wait.db"
    with sqlite3.connect(db) as conn:
        snapshots.ensure_table(conn)
        conn.execute("CREATE TABLE plate_appearances (batter_id TEXT, game_date TEXT, is_hit INTEGER)")
        _snap(conn, "1", "MLB", "1+ Hit", 1, 90)         # no PA rows for SLATE yet
        conn.commit()
    grading.grade_slate(date(2026, 6, 1), db_path=db)
    assert _result(db, "1") == (None, None)              # pending, not void

    with sqlite3.connect(db) as conn:                    # results now arrive
        conn.execute("INSERT INTO plate_appearances VALUES ('1', ?, 1)", (SLATE,))
        conn.commit()
    grading.grade_slate(date(2026, 6, 1), db_path=db)
    assert _result(db, "1") == ("hit", 1.0)              # graded once data is present


def test_void_reason_recorded(tmp_path):
    db = tmp_path / "vr.db"
    with sqlite3.connect(db) as conn:
        snapshots.ensure_table(conn)
        conn.execute("CREATE TABLE plate_appearances (batter_id TEXT, game_date TEXT, is_hit INTEGER)")
        _snap(conn, "1", "MLB", "1+ Hit", 1, 90)     # bats
        _snap(conn, "2", "MLB", "1+ Hit", 1, 88)     # did not bat → void with a reason
        conn.execute("INSERT INTO plate_appearances VALUES ('1', ?, 1)", (SLATE,))
        conn.commit()
    grading.grade_slate(date(2026, 6, 1), db_path=db)
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        vr = {r["player_id"]: r["void_reason"]
              for r in conn.execute("SELECT player_id, void_reason FROM opportunity_snapshots")}
    assert vr["1"] is None and vr["2"] == "did not bat"


def test_score_bands_and_small_sample():
    from services.grading import band_of, record, summarize_by_band
    assert band_of(70) == "70–74" and band_of(77) == "75–79" and band_of(99) == "99–100"
    rows = [{"opportunity_score": s, "result": r} for s, r in
            [(77, "hit"), (77, "miss"), (99, "hit"), (99, "hit"), (91, "void")]]
    bands = summarize_by_band(rows, min_sample=2)
    assert record(bands["75–79"]) == "1–1" and bands["75–79"]["hit_rate"] == 0.5
    assert bands["99–100"]["small_sample"] is False       # 2 decided ≥ 2
    assert bands["90–94"]["small_sample"] is True          # 0 decided (1 void) < 2
    assert list(bands) == ["75–79", "90–94", "99–100"]     # canonical order, present only


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
        _snap(conn, "1", "MLB", "5+ Strikeouts (SP)", 5, 80)      # over: 7 K → hit
        _snap(conn, "1", "MLB", "≤ 5 Hits Allowed (SP)", 5, 78)   # under: 4 hits → hit
        _snap(conn, "2", "MLB", "≤ 4 Strikeouts (SP)", 4, 70)     # under: 3 K → hit
        _snap(conn, "2", "MLB", "6+ Hits Allowed (SP)", 6, 72)    # over: 8 hits → hit
        _snap(conn, "1", "MLB", "6+ Hits Allowed (SP)", 6, 65)    # over: 4 hits → miss
        _snap(conn, "3", "MLB", "5+ Strikeouts (SP)", 5, 60)      # non-starter → void
        conn.commit()
    return db


def test_grade_sp_both_directions(tmp_path):
    db = _seed_sp(tmp_path)
    grading.grade_slate(date(2026, 6, 1), db_path=db)
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = {(r["player_id"], r["market"]): (r["result"], r["actual_value"])
                for r in conn.execute("SELECT player_id, market, result, actual_value "
                                      "FROM opportunity_snapshots")}
    # P1: 7 K, 4 hits
    assert rows[("1", "5+ Strikeouts (SP)")] == ("hit", 7.0)       # over: 7 ≥ 5
    assert rows[("1", "≤ 5 Hits Allowed (SP)")] == ("hit", 4.0)    # under: 4 ≤ 5
    assert rows[("1", "6+ Hits Allowed (SP)")] == ("miss", 4.0)    # over: 4 < 6 → miss
    # P2: 3 K, 8 hits
    assert rows[("2", "≤ 4 Strikeouts (SP)")] == ("hit", 3.0)      # under: 3 ≤ 4
    assert rows[("2", "6+ Hits Allowed (SP)")] == ("hit", 8.0)     # over: 8 ≥ 6 (the missed-over win)
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


# --- Phase 2: market breakdown, row classification, threshold slicing ---------

def _row(league, market, score, result):
    return {"league": league, "market": market, "player_id": "1", "player_name": "P",
            "opportunity_score": score, "result": result, "actual_value": 1.0}


def test_prop_type_of_row_and_present_types():
    from components.prop_filters import present_prop_types_rows, prop_type_of_row
    rows = [_row("MLB", "1+ Hit", 90, "hit"),
            _row("MLB", "6+ Strikeouts (SP)", 80, "miss"),
            _row("WNBA", "15+ Points", 70, "hit")]
    assert prop_type_of_row(rows[0]) == "hits"
    assert prop_type_of_row(rows[1]) == "sp_k"
    # canonical order: hits, sp_k, ..., points
    assert present_prop_types_rows(rows) == ["hits", "sp_k", "points"]


def test_summarize_by_market_splits_hit_rates():
    rows = [
        _row("MLB", "1+ Hit", 95, "hit"), _row("MLB", "1+ Hit", 90, "hit"),
        _row("MLB", "1+ Hit", 88, "miss"), _row("MLB", "1+ Hit", 80, "void"),
        _row("MLB", "6+ Strikeouts (SP)", 92, "miss"),
        _row("MLB", "6+ Strikeouts (SP)", 85, "miss"),
    ]
    bm = grading.summarize_by_market(rows)
    assert list(bm) == ["hits", "sp_k"]                 # canonical order preserved
    assert bm["hits"]["hit_rate"] == 2 / 3               # void excluded (2 hit / 3 decided)
    assert bm["hits"]["void"] == 1
    assert bm["sp_k"]["hit_rate"] == 0.0                 # 0 of 2


def test_market_breakdown_html_needs_two_markets():
    from components.results_feed import market_breakdown_html
    one = grading.summarize_by_market([_row("MLB", "1+ Hit", 90, "hit")])
    assert market_breakdown_html(one) == ""             # single market → nothing
    two = grading.summarize_by_market(
        [_row("MLB", "1+ Hit", 90, "hit"), _row("MLB", "6+ Strikeouts (SP)", 90, "miss")])
    html = market_breakdown_html(two)
    assert "By market" in html and "Batter Hits" in html and "SP Strikeouts" in html
    assert html.count("<div") == html.count("</div>")


# --- NFL grading (2026-08-18) -------------------------------------------------------

def test_nfl_props_stay_pending_until_the_weekly_feed_covers_that_date():
    """NFL feeds land weekly, not nightly. A Sunday slate can legitimately sit ungraded
    for days — pending keeps that honest, where void would freeze every prop as a
    non-result the moment it was captured, and grading is idempotent."""
    from services import grading

    row = {"league": "NFL", "market": "3+ Receptions", "market_key": "nfl_receptions",
           "direction": "over", "threshold": 3, "player_id": "p1",
           "snapshot_date": "2026-09-13", "game_id": "g1"}
    # Feed has not reached this week.
    result = grading._grade_row(row, {}, {}, {}, {}, {}, set(), {"mlb": True},
                                {}, set())
    assert result == (None, None, None), "must be pending, not void"


def test_nfl_prop_grades_against_the_feed_once_it_lands():
    from services import grading

    row = {"league": "NFL", "market": "60+ Rush Yards", "market_key": "nfl_rush_yds",
           "direction": "over", "threshold": 60, "player_id": "p1",
           "snapshot_date": "2026-09-13", "game_id": "g1"}
    lines = {"p1": {"rushing_yds": 84.0, "receiving_rec": 2.0}}
    covered = {"2026-09-13"}
    assert grading._grade_row(row, {}, {}, {}, {}, {}, set(), {"mlb": True},
                             lines, covered) == ("hit", 84.0, None)
    row["threshold"] = 100
    assert grading._grade_row(row, {}, {}, {}, {}, {}, set(), {"mlb": True},
                             lines, covered)[0] == "miss"


def test_a_player_who_did_not_appear_is_void_not_a_miss():
    """Same rule as a scratched batter: absence is not a wrong prediction."""
    from services import grading

    row = {"league": "NFL", "market": "4+ Receptions", "market_key": "nfl_receptions",
           "direction": "over", "threshold": 4, "player_id": "missing",
           "snapshot_date": "2026-09-13", "game_id": "g1"}
    result, actual, reason = grading._grade_row(
        row, {}, {}, {}, {}, {}, set(), {"mlb": True},
        {"p1": {"receiving_rec": 5.0}}, {"2026-09-13"})
    assert result == "void" and reason == "did not appear"
