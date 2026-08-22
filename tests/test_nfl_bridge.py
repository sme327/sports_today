"""The ESPN ↔ vendor-feed id bridge for NFL.

Offline: every test builds its own tiny SQLite feed, so nothing depends on which seasons
happen to be ingested on this machine.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime


from domain.models import SlateGame
from services.nfl_bridge import (canonical_team, coverage, feed_game_id, has_deep_dive,
                                 unavailable_reason)

_TEAMS = [
    ("SFO", "SFO", "San Francisco 49ers", "San Francisco", "49ers"),
    ("PHI", "PHI", "Philadelphia Eagles", "Philadelphia", "Eagles"),
    ("BUF", "BUF", "Buffalo Bills", "Buffalo", "Bills"),
    ("JAX", "JAX", "Jacksonville Jaguars", "Jacksonville", "Jaguars"),
]


def _db(tmp_path, rows=(("46033-SFO@PHI", "2026-01-11", 2025, 19,
                         "Philadelphia Eagles", "San Francisco 49ers"),)):
    p = tmp_path / "t.db"
    with sqlite3.connect(p) as c:
        c.execute("""CREATE TABLE nfl_teams (initial TEXT, nfl_initial TEXT,
                     long_name TEXT, short_name TEXT, nick_name TEXT)""")
        c.executemany("INSERT INTO nfl_teams VALUES (?,?,?,?,?)", _TEAMS)
        c.execute("""CREATE TABLE nfl_team_games (game_id TEXT, game_date TEXT, season INT,
                     week INT, team TEXT, opponent TEXT, venue TEXT)""")
        for gid, gd, season, week, home, away in rows:
            c.execute("INSERT INTO nfl_team_games VALUES (?,?,?,?,?,?,'Home')",
                      (gid, gd, season, week, home, away))
            c.execute("INSERT INTO nfl_team_games VALUES (?,?,?,?,?,?,'Road')",
                      (gid, gd, season, week, away, home))
    from services import nfl_bridge
    nfl_bridge._team_aliases.cache_clear()
    return p


def _game(away="San Francisco 49ers", home="Philadelphia Eagles",
          when="2026-01-11T18:00:00+00:00", league="NFL", phase="postseason", season=2025):
    return SlateGame(league=league, game_id="401772980", away_name=away, home_name=home,
                     away_short=away.split()[-1], home_short=home.split()[-1],
                     start_time=datetime.fromisoformat(when), phase=phase, season=season)


def test_matches_a_live_game_to_its_feed_row(tmp_path):
    """The whole point: ESPN keys games by event id (401772980), the feed by
    `46033-SFO@PHI`. Nothing translated between them, so a live NFL game had no deep dive
    while a full page sat in the archive."""
    db = _db(tmp_path)
    assert feed_game_id(_game(), db) == "46033-SFO@PHI"
    assert has_deep_dive(_game(), db) is True


def test_matches_across_a_utc_date_boundary(tmp_path):
    """ESPN start times are UTC, so a Sunday-night kickoff lands on Monday while the feed
    records the local calendar date. Without a one-day window those games never match."""
    db = _db(tmp_path)
    late = _game(when="2026-01-12T01:20:00+00:00")     # 8:20pm ET Sunday = Monday UTC
    assert feed_game_id(late, db) == "46033-SFO@PHI"


def test_home_and_away_are_not_interchangeable(tmp_path):
    """A reversed fixture is a different game. Matching on an unordered team pair would
    silently serve the wrong matchup page."""
    db = _db(tmp_path)
    flipped = _game(away="Philadelphia Eagles", home="San Francisco 49ers")
    assert feed_game_id(flipped, db) is None


def test_resolves_nicknames_and_initials(tmp_path):
    db = _db(tmp_path)
    assert canonical_team("49ers", db) == "San Francisco 49ers"
    assert canonical_team("SFO", db) == "San Francisco 49ers"
    assert canonical_team("San Francisco", db) == "San Francisco 49ers"
    assert canonical_team("Nonexistent FC", db) is None
    # A schedule that only gives the nickname still matches a feed row.
    assert feed_game_id(_game(away="49ers", home="Eagles"), db) == "46033-SFO@PHI"


def test_preseason_returns_none_with_a_reason_that_names_the_cause(tmp_path):
    """The feed carries regular season and playoffs only, so preseason never matches.
    That is ordinary, not an error — and the reader should be told which it is."""
    db = _db(tmp_path)
    pre = _game(away="Buffalo Bills", home="Jacksonville Jaguars",
                when="2026-08-13T23:00:00+00:00", phase="preseason", season=2026)
    assert feed_game_id(pre, db) is None
    assert has_deep_dive(pre, db) is False
    assert "preseason" in unavailable_reason(pre, db).lower()


def test_unloaded_season_says_so_and_names_what_is_held(tmp_path):
    db = _db(tmp_path)
    future = _game(when="2026-09-14T17:00:00+00:00", phase="regular", season=2026)
    assert feed_game_id(future, db) is None
    reason = unavailable_reason(future, db)
    assert "2026" in reason and "2025" in reason


def test_non_nfl_and_undated_games_are_refused(tmp_path):
    db = _db(tmp_path)
    assert feed_game_id(_game(league="MLB"), db) is None
    undated = SlateGame(league="NFL", game_id="x", away_name="San Francisco 49ers",
                        home_name="Philadelphia Eagles", start_time=None)
    assert feed_game_id(undated, db) is None


def test_missing_or_empty_database_is_not_a_crash(tmp_path):
    """A machine with no NFL feed loaded must render a slate, not raise."""
    assert feed_game_id(_game(), tmp_path / "nope.db") is None
    assert coverage(tmp_path / "nope.db") == {"seasons": [], "latest_date": None}
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    from services import nfl_bridge
    nfl_bridge._team_aliases.cache_clear()
    assert feed_game_id(_game(), empty) is None
    assert "no nfl season feed" in unavailable_reason(_game(), empty).lower()


def test_coverage_reports_what_is_loaded(tmp_path):
    db = _db(tmp_path, rows=(
        ("46033-SFO@PHI", "2026-01-11", 2025, 19, "Philadelphia Eagles", "San Francisco 49ers"),
        ("45000-BUF@JAX", "2024-09-08", 2024, 1, "Jacksonville Jaguars", "Buffalo Bills"),
    ))
    cov = coverage(db)
    assert cov["seasons"] == [2024, 2025]
    assert cov["latest_date"] == "2026-01-11"
