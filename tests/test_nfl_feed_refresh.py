"""In-season NFL feed pickup during the daily rebuild.

Offline: every test points the refresher at its own temp directory and temp DB, so it
never touches the real Downloads folder or the real database.
"""

from __future__ import annotations

import sqlite3

import pytest

from services.nfl_feed_refresh import _SEARCH_DIRS, refresh
from tests.test_nfl_ingest import _PLAYER, _TEAM, _write


def _drop(tmp_path, team_name="01-12-2026-nfl-season-team-feed.xlsx",
          player_name="01-12-2026-nfl-season-player-feed.xlsx"):
    d = tmp_path / "Downloads"
    d.mkdir(exist_ok=True)
    _write(d / team_name, _TEAM)
    _write(d / player_name, _PLAYER)
    return d


def test_nothing_in_downloads_is_silent_not_an_error(tmp_path):
    """The common path, and the whole offseason. Must not look like a warning."""
    empty = tmp_path / "Downloads"
    empty.mkdir()
    r = refresh(tmp_path / "t.db", dirs=(empty,))
    assert r.status == "skipped"
    assert "no nfl feed pair" in r.message.lower()


def test_a_dropped_feed_pair_is_imported(tmp_path):
    db = tmp_path / "t.db"
    r = refresh(db, dirs=(_drop(tmp_path),))
    assert r.status == "imported"
    assert r.seasons == (2025,)
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM nfl_team_games").fetchone()[0] > 0


def test_the_same_feed_is_not_reimported_the_next_morning(tmp_path):
    """The rebuild runs daily and the player feed is ~9MB. Re-parsing an unchanged
    workbook every morning is pure waste, so the fingerprint short-circuits it."""
    db = tmp_path / "t.db"
    d = _drop(tmp_path)
    assert refresh(db, dirs=(d,)).status == "imported"
    second = refresh(db, dirs=(d,))
    assert second.status == "unchanged"
    with sqlite3.connect(db) as c:
        runs = c.execute("SELECT COUNT(*) FROM nfl_feed_runs WHERE status='imported'").fetchone()[0]
    assert runs == 1, "an unchanged feed must not write a second import run"


def test_force_overrides_the_fingerprint(tmp_path):
    db = tmp_path / "t.db"
    d = _drop(tmp_path)
    refresh(db, dirs=(d,))
    assert refresh(db, dirs=(d,), force=True).status == "imported"


def test_a_newer_feed_is_picked_up(tmp_path):
    """Next week's file has a different name and mtime, so it must import even though
    the previous one loaded fine."""
    db = tmp_path / "t.db"
    d = _drop(tmp_path)
    assert refresh(db, dirs=(d,)).status == "imported"
    _write(d / "01-19-2026-nfl-season-team-feed.xlsx", _TEAM)
    _write(d / "01-19-2026-nfl-season-player-feed.xlsx", _PLAYER)
    assert refresh(db, dirs=(d,)).status == "imported"


def test_only_downloads_is_searched_by_the_automated_path(tmp_path):
    """The first version searched the whole of ~/Documents and imported a feed it found
    in a personal folder. An automated daily job must not go hunting through someone's
    documents tree — Downloads is the deliberate drop location, as it is for MLB."""
    assert _SEARCH_DIRS == (__import__("pathlib").Path.home() / "Downloads",)


def test_a_broken_workbook_raises_so_the_caller_can_treat_it_as_non_fatal(tmp_path):
    """The pipeline catches this and records `nfl_error`; a bad NFL workbook must never
    take down the MLB daily update. What matters here is that it fails loudly rather than
    writing a half-loaded season."""
    d = tmp_path / "Downloads"
    d.mkdir()
    broken = [list(r) for r in _TEAM]
    broken[1][5] = "FINAL SCORE"                  # drift: `final` disappears
    _write(d / "01-12-2026-nfl-season-team-feed.xlsx", broken)
    _write(d / "01-12-2026-nfl-season-player-feed.xlsx", _PLAYER)
    with pytest.raises(ValueError, match="final"):
        refresh(tmp_path / "t.db", dirs=(d,))
