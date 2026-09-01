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
