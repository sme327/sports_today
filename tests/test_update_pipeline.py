"""Offline tests for the shared rebuild pipeline. The MLB import, web collectors,
and cloud publish are all faked via monkeypatch — no feed file, no network."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from services import update_pipeline as P

_MLB = {"plate_appearances": 10, "games": 2, "batters": 5, "pitchers": 4}


_ZERO = {"graded": 0, "hit": 0, "miss": 0, "void": 0, "pending": 0}


def _fake_import(monkeypatch):
    monkeypatch.setattr("src.ingest.import_feed", lambda p, **k: (Path("db"), _MLB))
    # Don't touch the real ledger during the pipeline's regrade step.
    monkeypatch.setattr("services.grading.grade_slate", lambda d, **k: dict(_ZERO))


def test_rebuild_mlb_only(monkeypatch):
    _fake_import(monkeypatch)
    monkeypatch.setattr("services.data_store.is_configured", lambda: False)
    out = P.rebuild("feed.xlsx", collect_web=False)
    assert out["mlb"] == _MLB
    assert "wnba" not in out and "mls" not in out
    assert out["published"] is False


def test_rebuild_with_collectors(monkeypatch):
    _fake_import(monkeypatch)
    monkeypatch.setattr("src.wnba_collector.collect_wnba_season",
                        lambda **k: SimpleNamespace(games_downloaded=3, player_rows_written=60))
    monkeypatch.setattr("src.mls_collector.collect",
                        lambda **k: SimpleNamespace(events_collected=1, standings_rows=30))
    monkeypatch.setattr("services.data_store.is_configured", lambda: True)
    monkeypatch.setattr("services.data_store.publish_db", lambda: True)
    out = P.rebuild("feed.xlsx")
    assert out["wnba"] == {"games": 3, "rows": 60}
    assert out["mls"] == {"matches": 1, "standings": 30}
    assert out["published"] is True


def test_collector_failure_is_captured(monkeypatch):
    _fake_import(monkeypatch)

    def boom(**k):
        raise RuntimeError("no internet")

    monkeypatch.setattr("src.wnba_collector.collect_wnba_season", boom)
    monkeypatch.setattr("src.mls_collector.collect", boom)
    monkeypatch.setattr("services.data_store.is_configured", lambda: False)
    out = P.rebuild("feed.xlsx")
    assert out["mlb"] == _MLB                     # required step still succeeded
    assert "no internet" in out["wnba_error"]
    assert "no internet" in out["mls_error"]
    assert out["published"] is False
