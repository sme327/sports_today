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
    # Recording game outcomes fetches finished slates, so it must be faked here too —
    # this file's contract is that the pipeline runs with no network at all.
    monkeypatch.setattr("scripts.record_game_outcomes.run", lambda **k: 7)
    # Collectors added to rebuild() after this file was written. Each is a network call
    # — the NFL schedule alone is eighteen — and leaving them live took the suite from
    # ~50s to over four minutes while quietly breaking this file's stated contract that
    # it runs with no network at all.
    # NCAAF and the prior-season backfill were never stubbed either. They mostly no-op
    # (both skip work they have already done), so they were cheap enough to hide — but
    # "cheap network" is still network, and this file says it makes none.
    # The web collectors belong here too, not only in the one test that asserts on their
    # values — a fake that is complete is the thing the no-network guard below can lean
    # on. Tests that care about specific counts still override these afterwards.
    monkeypatch.setattr("src.wnba_collector.collect_wnba_season",
                        lambda **k: SimpleNamespace(games_downloaded=0, player_rows_written=0))
    monkeypatch.setattr("src.mls_collector.collect",
                        lambda **k: SimpleNamespace(events_collected=0, standings_rows=0))
    monkeypatch.setattr("src.ncaaf_collector.collect",
                        lambda **k: {"teams": 0, "passers": 0, "team_seasons": 0,
                                     "skipped": 0})
    monkeypatch.setattr("src.prior_season_collector.have_season", lambda *a, **k: True)
    monkeypatch.setattr("src.standings_collector.collect", lambda *a, **k: {"MLB": 30})
    monkeypatch.setattr("src.standings_collector.collect_mls_teams", lambda *a, **k: 30)
    monkeypatch.setattr("src.nfl_schedule.collect", lambda *a, **k: 272)
    monkeypatch.setattr(
        "services.daily_feed.precompute_days",
        lambda days: [{"date": d.isoformat(), "games": 0, "opportunities": 0,
                       "ledger_rows": 0, "schedule_seconds": 0,
                       "scoring_seconds": 0, "total_seconds": 0} for d in days],
    )


def test_rebuild_mlb_only(monkeypatch):
    _fake_import(monkeypatch)
    monkeypatch.setattr("services.data_store.is_configured", lambda: False)
    out = P.rebuild("feed.xlsx", collect_web=False)
    assert out["mlb"] == _MLB
    assert "wnba" not in out and "mls" not in out
    assert out["published"] is False
    assert len(out["daily_feed"]) == P.SLATE_DAYS


def test_rebuild_with_collectors(monkeypatch):
    _fake_import(monkeypatch)
    # The import is deliberately faked and returns no real SQLite file; fake the slim
    # builder too so this offline test exercises which artifact the pipeline publishes,
    # not whether SQLite can copy a nonexistent fixture.
    monkeypatch.setattr("scripts.build_deploy_db.build",
                        lambda src, dst: Path(dst))
    monkeypatch.setattr("src.wnba_collector.collect_wnba_season",
                        lambda **k: SimpleNamespace(games_downloaded=3, player_rows_written=60))
    monkeypatch.setattr("src.mls_collector.collect",
                        lambda **k: SimpleNamespace(events_collected=1, standings_rows=30))
    monkeypatch.setattr("services.data_store.is_configured", lambda: True)
    # The real publish_db takes the file to upload; a zero-arg fake would pass while the
    # pipeline actually publishes the *slim* build, which is the behaviour that matters.
    published: list = []
    monkeypatch.setattr("services.data_store.publish_db",
                        lambda src=None: (published.append(src), True)[1])
    out = P.rebuild("feed.xlsx")
    assert out["wnba"] == {"games": 3, "rows": 60}
    assert out["mls"] == {"matches": 1, "standings": 30}
    assert out["published"] is True
    assert published and published[0] is not None
    assert published[0].name == "sportshub-deploy.db", (
        "the deployed copy must be the slim build, not the working database")


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


def test_game_outcomes_are_recorded_and_non_fatal(monkeypatch):
    """The editorial feedback loop runs with the daily rebuild, and a failure there
    must not fail the rebuild — it is analysis, not data the app needs to boot."""
    _fake_import(monkeypatch)
    monkeypatch.setattr("services.data_store.is_configured", lambda: False)
    assert P.rebuild("feed.xlsx", collect_web=False)["game_outcomes"] == 7

    def _boom(**_k):
        raise RuntimeError("espn down")
    monkeypatch.setattr("scripts.record_game_outcomes.run", _boom)
    out = P.rebuild("feed.xlsx", collect_web=False)
    assert "espn down" in out["game_outcomes_error"]
    assert out["mlb"], "the rebuild itself still succeeded"


# --- refreshing the slate without the MLB feed (2026-08-29) --------------------------

def test_rebuild_can_skip_the_mlb_import_entirely(monkeypatch):
    """Today's and tomorrow's games come from the schedule sources, not the workbook, so
    the slate must be refreshable on a morning the vendor file has not arrived."""
    _fake_import(monkeypatch)
    monkeypatch.setattr("services.data_store.is_configured", lambda: False)

    def _must_not_import(*a, **k):
        raise AssertionError("the workbook must not be imported when import_mlb=False")

    monkeypatch.setattr("src.ingest.import_feed", _must_not_import)

    out = P.rebuild("feed.xlsx", collect_web=False, import_mlb=False)
    assert "mlb" not in out                      # nothing claimed about a feed we skipped
    assert len(out["daily_feed"]) == P.SLATE_DAYS   # every slate day still precomputed
    assert "regraded" in out


def test_regrade_summary_counts_props_not_snapshot_rows(monkeypatch):
    """The terminal and the Results page must report the same record for the same day.

    `grade_slate` counts snapshot *rows*, and a slate precomputed the evening before
    holds two captures of every prop — so the run summary read ~2x the day's real
    record (431/344/214 printed against the 219/175/108 the app showed).
    """
    _fake_import(monkeypatch)
    monkeypatch.setattr("services.data_store.is_configured", lambda: False)
    # Rows touched: double-counted, as the real grader reports them.
    monkeypatch.setattr("services.grading.grade_slate",
                        lambda d, **k: {"graded": 20, "hit": 8, "miss": 8, "void": 4,
                                        "pending": 0})
    # What the deduped ledger actually holds: one row per prop, latest capture.
    props = [{"result": "hit"}] * 4 + [{"result": "miss"}] * 4 + [{"result": "void"}] * 2
    monkeypatch.setattr("services.grading.load_graded_slate", lambda d, **k: list(props))

    out = P.rebuild("feed.xlsx", collect_web=False)

    assert out["regraded"], "the regrade step must still report something"
    for day in out["regraded"].values():
        assert day == {"hit": 4, "miss": 4, "void": 2}


def test_slate_days_matches_the_web_layer_day_map():
    """Three days get precomputed and three get exported, or the roll-over breaks.

    `services` may not import `web` (test_layering), so the count lives in both places.
    If they drift, the browser rolls onto a day the build never computed and the page
    goes blank — hence this assertion rather than a shared import.
    """
    from web.today import DAY_OFFSETS

    assert P.SLATE_DAYS == len(DAY_OFFSETS)
    # Contiguous from today: the roll-over indexes DAY_PAGES by elapsed days, so a gap
    # would silently skip a day rather than fail.
    assert sorted(DAY_OFFSETS.values()) == list(range(P.SLATE_DAYS))


def test_rebuild_precomputes_every_slate_day(monkeypatch):
    _fake_import(monkeypatch)
    monkeypatch.setattr("services.data_store.is_configured", lambda: False)
    out = P.rebuild("feed.xlsx", collect_web=False)
    assert len(out["daily_feed"]) == P.SLATE_DAYS

    from datetime import date as _date
    from datetime import timedelta as _td
    expected = [(_date.today() + _td(days=n)).isoformat() for n in range(P.SLATE_DAYS)]
    assert [feed["date"] for feed in out["daily_feed"]] == expected


def test_the_pipeline_tests_really_make_no_network_calls(monkeypatch):
    """This file's contract, enforced rather than asserted in prose.

    Every collector added to ``rebuild`` has to be stubbed here, and twice now one was
    not: the NFL season schedule (eighteen requests) and the standings collectors took
    this file from ~50s to over four minutes of real HTTP while every test still passed.
    Nothing failed, so nothing said so.

    Blocking the socket makes the omission loud: a future collector wired into rebuild
    without a fake fails here instead of quietly slowing the suite down.
    """
    import socket

    def _blocked(*args, **kwargs):
        raise AssertionError("the pipeline tests must not open a network connection")

    _fake_import(monkeypatch)
    monkeypatch.setattr("services.data_store.is_configured", lambda: False)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)

    out = P.rebuild("feed.xlsx", collect_web=True)
    assert "daily_feed" in out
