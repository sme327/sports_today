"""The NFL season schedule, browsable by week or by team.

Separate from ``nfl_team_games``, which holds *played* games from the ingested vendor
seasons and exists to answer analytical questions. This is the forward schedule from
ESPN — a different question of a different source, deliberately not joined.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src import nfl_schedule
from web import nfl_schedule_view


def _row(week, away, home, when, gid=None, **kw):
    return dict(
        season=2026, week=week, game_id=gid or f"{week}{away}{home}",
        start_time=when, venue=f"{home} Field",
        away_id="1", away_name=f"{away} Team", away_abbr=away, away_logo="a.png",
        home_id="2", home_name=f"{home} Team", home_abbr=home, home_logo="h.png",
        status=kw.get("status", "pre"), away_score=kw.get("away_score"),
        home_score=kw.get("home_score"), collected_at="x")


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "s.db"
    conn = sqlite3.connect(path)
    nfl_schedule.ensure_tables(conn)
    soon = datetime.now(timezone.utc) + timedelta(days=3)
    past = datetime.now(timezone.utc) - timedelta(days=7)
    nfl_schedule.upsert(conn, [
        _row(1, "SF", "LAR", past.isoformat(), status="post", away_score=24, home_score=17),
        _row(2, "SF", "SEA", soon.isoformat()),
        _row(2, "NE", "BUF", (soon + timedelta(hours=3)).isoformat()),
        _row(3, "ARI", "SF", (soon + timedelta(days=7)).isoformat()),
    ])
    conn.commit()
    return path


def test_a_team_view_shows_only_that_team_and_names_the_week(db):
    """Following one team is the other axis of the same table — 'who do we still have'
    rather than 'what is on this weekend'."""
    ctx = nfl_schedule_view.build_context({"team": "SF"}, db_path=db)
    assert ctx["mode"] == "team" and ctx["team"] == "SF"
    assert ctx["game_count"] == 3
    assert all(g["show_week"] for g in ctx["groups"][0]["games"])


def test_a_week_view_groups_by_day(db):
    ctx = nfl_schedule_view.build_context({"week": "2"}, db_path=db)
    assert ctx["mode"] == "week" and ctx["week"] == 2
    assert ctx["game_count"] == 2


def test_the_default_week_is_the_next_one_with_a_game_left(db):
    """Landing on week 1 in December would be useless. The default follows the season."""
    ctx = nfl_schedule_view.build_context({}, db_path=db)
    assert ctx["week"] == 2


def test_unknown_team_or_week_falls_back_rather_than_emptying_the_page(db):
    assert nfl_schedule_view.build_context({"team": "XXX"}, db_path=db)["mode"] == "week"
    assert nfl_schedule_view.build_context({"week": "99"}, db_path=db)["week"] == 2


def test_a_played_game_shows_its_score_instead_of_a_kickoff(db):
    ctx = nfl_schedule_view.build_context({"week": "1"}, db_path=db)
    game = ctx["groups"][0]["games"][0]
    assert game["final"] is True and game["away_score"] == 24


def test_no_collected_schedule_is_an_honest_empty_page(tmp_path):
    conn = sqlite3.connect(tmp_path / "empty.db")
    nfl_schedule.ensure_tables(conn)
    conn.commit()
    ctx = nfl_schedule_view.build_context({}, db_path=tmp_path / "empty.db")
    assert ctx["groups"] == [] if "groups" in ctx else ctx["games"] == []


def test_the_export_seeds_every_week_and_every_team():
    """A menu link to a page the exporter never built is one dead link *per page* —
    the NFL archive proved that with 640 of them. Both axes are enumerated."""
    from web.management.commands.export_static import _NFL_SCHEDULE_SEEDS, _SEEDS

    assert "/nfl/schedule/" in _SEEDS
    weeks = [s for s in _NFL_SCHEDULE_SEEDS if "week=" in s]
    teams = [s for s in _NFL_SCHEDULE_SEEDS if "team=" in s]
    assert len(weeks) >= 18 and len(teams) >= 32


def test_the_crawler_bound_still_excludes_the_archive():
    """The schedule is allowed with its two known controls; everything else under /nfl/
    stays out, which is what keeps the archive's per-week pages from exploding the crawl."""
    from web.management.commands.export_static import should_crawl

    assert should_crawl("/nfl/schedule/")
    assert should_crawl("/nfl/schedule/?week=5")
    assert should_crawl("/nfl/schedule/?team=SF")
    assert not should_crawl("/nfl/schedule/?anything=else")
    assert not should_crawl("/nfl/")
    assert not should_crawl("/nfl/?season=2025&week=4")
