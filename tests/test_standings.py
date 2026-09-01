"""Standings: the reference point the MLB matchup page was missing.

The sliders describe *how* a team plays and never whether they are any good, so a reader
had nothing on the page denominated in wins. These cover the reading and formatting of
that anchor, and the two rules it must not break: joined on ids rather than names, and
bounded by the slate date so a rebuilt page does not re-date history.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from services import standings
from src import standings_store


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "s.db"
    conn = sqlite3.connect(path)
    standings_store.ensure_tables(conn)
    rows = [
        dict(league="MLB", season=2026, snapshot_date="2026-08-31", team_id="139",
             team_name="Rays", team_abbr=None, conference="American League",
             division="American League East", division_rank=1, wins=82, losses=54,
             ties=0, win_pct=.603, games_behind=0.0, playoff_seed=None, streak="W4",
             last_ten="6-4", home_record="45-25", road_record="37-29", collected_at="x"),
        dict(league="MLB", season=2026, snapshot_date="2026-08-31", team_id="147",
             team_name="Yankees", team_abbr=None, conference="American League",
             division="American League East", division_rank=2, wins=78, losses=59,
             ties=0, win_pct=.569, games_behind=4.5, playoff_seed=None, streak="L1",
             last_ten="5-5", home_record="40-30", road_record="38-29", collected_at="x"),
        # An older day, to prove the as_of bound picks the right snapshot.
        dict(league="MLB", season=2026, snapshot_date="2026-08-01", team_id="139",
             team_name="Rays", team_abbr=None, conference="American League",
             division="American League East", division_rank=3, wins=60, losses=48,
             ties=0, win_pct=.556, games_behind=6.0, playoff_seed=None, streak="L2",
             last_ten="4-6", home_record="33-20", road_record="27-28", collected_at="x"),
    ]
    standings_store.upsert(conn, rows)
    conn.commit()
    return path


def test_the_leader_is_not_told_how_far_behind_it_is(db):
    """A leader's games back is 0, and "0 GB" on the team in first reads as a deficit."""
    table = standings.for_league("MLB", db_path=db)
    assert table["139"].place == "1st in AL East"
    assert table["139"].summary == "82-54 · 1st in AL East"


def test_a_chaser_carries_its_deficit(db):
    table = standings.for_league("MLB", db_path=db)
    assert table["147"].place == "2nd in AL East, 4.5 GB"
    assert table["147"].summary == "78-59 · 2nd in AL East, 4.5 GB"


def test_long_division_names_are_shortened(db):
    """"American League East" crowds a hero line that already carries a record."""
    assert standings.for_league("MLB", db_path=db)["139"].division_short == "AL East"


def test_as_of_reads_the_standings_as_they_stood(db):
    """A matchup page rebuilt in October must describe an August game with August's
    records — the same leakage rule the rest of the project follows."""
    august = standings.for_league("MLB", date(2026, 8, 15), db_path=db)
    assert august["139"].summary == "60-48 · 3rd in AL East, 6 GB"
    later = standings.for_league("MLB", date(2026, 9, 30), db_path=db)
    assert later["139"].summary == "82-54 · 1st in AL East"


def test_a_date_before_any_snapshot_yields_nothing(db):
    """Absent standings must be absent, never the nearest available guess."""
    assert standings.for_league("MLB", date(2026, 1, 1), db_path=db) == {}


def test_pair_for_joins_on_ids_and_tolerates_a_missing_team(db):
    away, home = standings.pair_for("MLB", "147", "139", date(2026, 8, 31), db_path=db)
    assert (away.team_name, home.team_name) == ("Yankees", "Rays")
    missing, _ = standings.pair_for("MLB", "999", "139", date(2026, 8, 31), db_path=db)
    assert missing is None


def test_a_sport_with_ties_shows_all_three_numbers(db):
    conn = sqlite3.connect(db)
    standings_store.upsert(conn, [dict(
        league="NFL", season=2026, snapshot_date="2026-08-31", team_id="1",
        team_name="Team", team_abbr=None, conference="AFC", division="AFC North",
        division_rank=1, wins=9, losses=6, ties=1, win_pct=.594, games_behind=0.0,
        playoff_seed=1, streak="W2", last_ten="6-4", home_record="5-3",
        road_record="4-3", collected_at="x")])
    conn.commit()
    assert standings.for_league("NFL", db_path=db)["1"].record == "9-6-1"


def test_mlb_standings_do_not_come_from_espn():
    """MLB is scheduled from StatsAPI, so its team ids are StatsAPI ids. ESPN's
    standings carry ESPN ids; pairing them would mean joining on team *names*, which
    this project refuses. The collector must keep MLB on its own source."""
    from src.standings_collector import LEAGUES

    assert "MLB" not in LEAGUES, "MLB must not be fetched from the ESPN standings map"


# --- The page -------------------------------------------------------------------------

def test_the_standings_page_groups_by_division_and_marks_the_leader(db):
    from web import standings_view

    context = standings_view.build_context("MLB", db_path=db)
    assert context["league"] == "MLB"
    group = context["groups"][0]
    assert group["name"] == "American League East"
    assert [t["name"] for t in group["teams"]] == ["Rays", "Yankees"]
    assert group["teams"][0]["leader"] is True
    assert group["teams"][1]["leader"] is False


def test_the_leaders_games_behind_column_is_a_dash_not_a_zero(db):
    """"0.0" in a GB column reads as a deficit. The dash is the scoreboard convention
    and the same reasoning as the hero line, which omits it entirely."""
    from web import standings_view

    teams = standings_view.build_context("MLB", db_path=db)["groups"][0]["teams"]
    assert teams[0]["games_behind"] == "—"
    assert teams[1]["games_behind"] == "4.5"


def test_an_unknown_league_falls_back_rather_than_erroring(db):
    from web import standings_view

    assert standings_view.build_context("CRICKET", db_path=db)["league"] == "MLB"


def test_no_standings_at_all_is_an_honest_empty_page(tmp_path):
    """A league with nothing loaded must say so, not render an empty table."""
    import sqlite3

    from src import standings_store
    from web import standings_view

    empty = tmp_path / "empty.db"
    standings_store.ensure_tables(sqlite3.connect(empty))
    context = standings_view.build_context(None, db_path=empty)
    assert context["league"] is None and context["groups"] == []


def test_the_page_says_it_is_not_a_projection():
    """A standings table is the most forecast-looking surface in the product; the
    product rule is that it states what it is not."""
    from pathlib import Path

    html = Path("web/templates/web/standings.html").read_text(encoding="utf-8")
    assert "not a projection" in html


def test_every_league_page_is_exported():
    """Reachable from the menu means nothing if the static build never wrote the page."""
    from web.management.commands.export_static import _SEEDS

    assert "/standings/" in _SEEDS
    for league in ("MLB", "NFL", "NBA", "NHL"):
        assert f"/standings/?league={league}" in _SEEDS


def test_a_league_that_has_not_started_is_not_listed(tmp_path):
    """Before the opener every team is 0-0, and a table of thirty-two zeroes tells a
    reader nothing while looking authoritative. On 1 September the NFL page rendered
    3-0 and 1-1-1 — ESPN's *preseason* records wearing a standings table."""
    import sqlite3

    from src import standings_store
    from web import standings_view

    db = tmp_path / "s.db"
    conn = sqlite3.connect(db)
    standings_store.ensure_tables(conn)
    from datetime import date as _date

    base = dict(season=2026, snapshot_date=_date.today().isoformat(), team_abbr=None,
                conference="AFC", division="AFC East", win_pct=0.0, games_behind=0.0,
                playoff_seed=None, streak=None, last_ten=None, home_record=None,
                road_record=None, collected_at="x")
    standings_store.upsert(conn, [
        dict(base, league="NFL", team_id="1", team_name="Bills",
             division_rank=1, wins=0, losses=0, ties=0),
        dict(base, league="MLB", team_id="2", team_name="Rays", conference="AL",
             division="AL East", division_rank=1, wins=82, losses=54, ties=0),
    ])
    conn.commit()

    assert standings_view.available_leagues(db_path=db) == ["MLB"]


def test_espn_standings_are_asked_for_the_regular_season():
    """Without seasontype=2 the endpoint serves preseason results."""
    from pathlib import Path

    src = Path("src/standings_collector.py").read_text(encoding="utf-8")
    assert "seasontype=2" in src


def test_a_future_dated_snapshot_is_never_served(tmp_path):
    """`date.today()` is local; `datetime.now(timezone.utc)` is not. A collector run in
    a UTC process writes tomorrow's snapshot_date, and MAX() then prefers it forever —
    which is exactly how a page came to serve future-dated preseason rows instead of
    the current table."""
    import sqlite3
    from datetime import date, timedelta

    from src import standings_store

    db = tmp_path / "s.db"
    conn = sqlite3.connect(db)
    standings_store.ensure_tables(conn)
    base = dict(season=2026, team_abbr=None, conference="AL", division="AL East",
                division_rank=1, ties=0, win_pct=.5, games_behind=0.0, playoff_seed=None,
                streak=None, last_ten=None, home_record=None, road_record=None,
                collected_at="x", league="MLB", team_id="139", team_name="Rays")
    today = date.today()
    standings_store.upsert(conn, [
        dict(base, snapshot_date=today.isoformat(), wins=82, losses=54),
        dict(base, snapshot_date=(today + timedelta(days=1)).isoformat(),
             wins=0, losses=0),
    ])
    conn.commit()

    assert standings_store.latest_snapshot(conn, "MLB") == today.isoformat()
    assert standings.for_league("MLB", db_path=db)["139"].wins == 82


# --- MLS: a league that is scored rather than won -------------------------------------

def _mls_db(tmp_path):
    import sqlite3
    db = tmp_path / "mls.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE mls_standings (season INT, team_id TEXT,
        snapshot_date TEXT, conference TEXT, conference_rank INT, league_rank INT,
        points INT, games_played INT, wins INT, draws INT, losses INT,
        goals_for INT, goals_against INT, goal_difference INT, collected_at TEXT)""")
    conn.execute("CREATE TABLE mls_teams (team_id TEXT PRIMARY KEY, name TEXT, abbr TEXT, logo TEXT)")
    conn.executemany("INSERT INTO mls_standings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        (2026, "18986", "2026-09-01", "Eastern Conference", 1, 1, 52, 22, 16, 4, 2, 50, 20, 30, "x"),
        (2026, "182", "2026-09-01", "Eastern Conference", 2, 4, 37, 21, 11, 4, 6, 33, 22, 11, "x"),
    ])
    conn.executemany("INSERT INTO mls_teams VALUES (?,?,?,?)", [
        ("18986", "Nashville SC", "NSH", "n.png"), ("182", "Chicago Fire FC", "CHI", "c.png")])
    conn.commit()
    return db


def test_mls_is_shown_as_points_not_games_behind(tmp_path):
    """Three points a win, one a draw. "Games behind" means nothing in a league where a
    draw is a result, so forcing MLS into the W-L-GB shape would misdescribe the sport."""
    from web import standings_view

    ctx = standings_view.build_context("MLS", db_path=_mls_db(tmp_path))
    assert ctx["points_table"] is True
    top = ctx["groups"][0]["teams"][0]
    assert top["points"] == 52 and top["record"] == "16-4-2"
    assert top["goal_difference"] == "+30"
    assert "games_behind" not in top


def test_mls_names_come_from_the_id_lookup(tmp_path):
    """mls_standings is keyed by team id and carries no names — the MLS schedule feed
    has none either. ESPN's table uses the same ids, so it supplies them."""
    from web import standings_view

    ctx = standings_view.build_context("MLS", db_path=_mls_db(tmp_path))
    assert [t["name"] for t in ctx["groups"][0]["teams"]] == ["Nashville SC", "Chicago Fire FC"]


def test_a_missing_mls_name_is_not_rendered_as_a_bare_id(tmp_path):
    import sqlite3

    from web import standings_view

    db = _mls_db(tmp_path)
    sqlite3.connect(db).execute("DELETE FROM mls_teams").connection.commit()
    teams = standings_view.build_context("MLS", db_path=db)["groups"][0]["teams"]
    assert all(t["name"].startswith("Team ") for t in teams)


def test_wnba_uses_the_shared_record_shape():
    """WNBA is scheduled from ESPN, so ESPN's standings ids match it natively — the
    same reason MLB must not come from there."""
    from src.standings_collector import LEAGUES

    assert "WNBA" in LEAGUES and "MLB" not in LEAGUES


def test_both_new_league_tables_are_exported():
    from web.management.commands.export_static import _SEEDS

    for league in ("WNBA", "MLS"):
        assert f"/standings/?league={league}" in _SEEDS
