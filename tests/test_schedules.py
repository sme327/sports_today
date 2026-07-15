from datetime import date

import pytest

from domain.models import SlateGame, SourceStatus
from services import schedule_cache
from services.schedules import get_slate


class _StubAdapter:
    league = "TEST"
    source_name = "Stub"

    def __init__(self, games=None, fail=False):
        self._games = games or []
        self._fail = fail

    def fetch_schedule(self, slate_date):
        if self._fail:
            raise RuntimeError("boom")
        return self._games


def _game():
    return SlateGame(league="TEST", game_id="1", away_short="A", home_short="B")


def test_live_success_is_live_and_cached(monkeypatch):
    import services.schedules as sched
    written = {}
    monkeypatch.setattr(sched.schedule_cache, "write", lambda **k: written.update(k))
    adapter = _StubAdapter(games=[_game()])
    games, status = get_slate(adapter, date(2026, 6, 1))
    assert status.status is SourceStatus.LIVE
    assert len(games) == 1
    assert written["status"] is SourceStatus.LIVE  # cached on success


def test_live_empty_is_empty_not_fallback(monkeypatch, tmp_db):
    monkeypatch.setattr(schedule_cache, "DB_PATH", tmp_db, raising=False)
    import services.schedules as sched
    monkeypatch.setattr(sched.schedule_cache, "write", lambda **k: None)
    monkeypatch.setattr(sched.schedule_cache, "read_latest_usable", lambda **k: None)
    adapter = _StubAdapter(games=[])
    games, status = get_slate(adapter, date(2026, 6, 1))
    assert games == []
    assert status.status is SourceStatus.EMPTY  # legitimate off day, no fallback


def test_live_failure_uses_cache(monkeypatch):
    import services.schedules as sched
    monkeypatch.setattr(
        sched.schedule_cache, "read_latest_usable",
        lambda **k: ([_game()], __import__("datetime").datetime(2026, 6, 1)),
    )
    adapter = _StubAdapter(fail=True)
    games, status = get_slate(adapter, date(2026, 6, 1))
    assert status.status is SourceStatus.CACHED
    assert len(games) == 1


def test_live_failure_no_cache_is_error(monkeypatch):
    import services.schedules as sched
    monkeypatch.setattr(sched.schedule_cache, "read_latest_usable", lambda **k: None)
    adapter = _StubAdapter(fail=True)
    games, status = get_slate(adapter, date(2026, 6, 1))
    assert status.status is SourceStatus.ERROR
    assert games == []
