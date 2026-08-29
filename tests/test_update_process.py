"""The operator-facing safety rails on the daily update: the stale-feed warning
and the per-run JSONL record. Both exist because the reader-facing freshness
banner tells the reader about a stale morning — but only the operator can fix one,
and only a persisted record can answer "did Tuesday's update actually work?"
after the terminal window has closed."""

from __future__ import annotations

import json
from datetime import date, datetime

from scripts.morning_update import append_run_log
from scripts.sync_mlb_download import staleness_warning


def test_a_feed_dated_yesterday_is_healthy():
    """The vendor file is season-to-date through the previous day, so a feed dated
    yesterday is exactly on time."""
    assert staleness_warning(datetime(2026, 8, 19), today=date(2026, 8, 20)) is None


def test_a_same_day_feed_is_healthy():
    assert staleness_warning(datetime(2026, 8, 20), today=date(2026, 8, 20)) is None


def test_an_old_feed_warns_with_its_age():
    warning = staleness_warning(datetime(2026, 8, 15), today=date(2026, 8, 20))
    assert warning is not None
    assert "2026-08-15" in warning
    assert "4 days" in warning


def test_one_day_behind_still_warns():
    """The boundary case: the newest feed stops the day before yesterday."""
    warning = staleness_warning(datetime(2026, 8, 18), today=date(2026, 8, 20))
    assert warning is not None
    assert "1 day older" in warning


def test_run_log_appends_one_json_line_per_run(tmp_path):
    log = tmp_path / "runs.jsonl"
    assert append_run_log({"run_at": "t1", "mlb": {"games": 2}}, path=log) is None
    assert append_run_log({"run_at": "t2", "error": "boom"}, path=log) is None
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert [row["run_at"] for row in rows] == ["t1", "t2"]
    assert rows[0]["mlb"] == {"games": 2}
    assert rows[1]["error"] == "boom"


def test_run_log_failure_is_reported_not_raised(tmp_path):
    """The record must never fail the update it records."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("a file sitting where the log's parent dir should be")
    error = append_run_log({"x": 1}, path=blocker / "runs.jsonl")
    assert error


# --- a forgotten download must not stop the day reaching the reader (2026-08-29) -----

def _run_update(monkeypatch, calls, *, downloads_raises=False, argv=None):
    """Drive scripts.morning_update.main with the pipeline faked out."""
    import sys

    from scripts import morning_update

    def fake_sync(downloads, force=False):
        if downloads_raises:
            raise FileNotFoundError("No dated MLB play-by-play workbook found")
        return (morning_update.CURRENT_FEED, True)

    def fake_rebuild(feed, *, import_mlb=True, **kw):
        calls["import_mlb"] = import_mlb
        return {"mlb": {"plate_appearances": 1, "games": 1, "batters": 1, "pitchers": 1},
                "daily_feed": [], "regraded": {}} if import_mlb else {
                "daily_feed": [], "regraded": {}}

    monkeypatch.setattr(morning_update, "sync_latest", fake_sync)
    monkeypatch.setattr(morning_update, "rebuild", fake_rebuild)
    monkeypatch.setattr(morning_update, "append_run_log", lambda r, **k: None)
    monkeypatch.setattr(sys, "argv", ["morning_update", *(argv or [])])
    return morning_update.main()


def test_a_missing_workbook_no_longer_ends_the_run(monkeypatch):
    """It used to raise here, and because update_and_publish.command runs under `set -e`
    the publish never happened either — a forgotten download left the site on the
    previous day's games."""
    calls: dict = {}
    assert _run_update(monkeypatch, calls, downloads_raises=True) == 0
    assert calls["import_mlb"] is False


def test_skip_mlb_never_looks_in_downloads(monkeypatch):
    """`--skip-mlb` is for the morning the file is not there yet. Searching Downloads
    anyway would reintroduce the failure it exists to avoid."""
    import sys

    from scripts import morning_update

    calls: dict = {}

    def explode(*a, **k):
        raise AssertionError("--skip-mlb must not search Downloads")

    def fake_rebuild(feed, *, import_mlb=True, **kw):
        calls["import_mlb"] = import_mlb
        return {"daily_feed": [], "regraded": {}}

    monkeypatch.setattr(morning_update, "sync_latest", explode)
    monkeypatch.setattr(morning_update, "rebuild", fake_rebuild)
    monkeypatch.setattr(morning_update, "append_run_log", lambda r, **k: None)
    monkeypatch.setattr(sys, "argv", ["morning_update", "--skip-mlb"])

    assert morning_update.main() == 0
    assert calls["import_mlb"] is False


def test_the_ordinary_run_still_imports(monkeypatch):
    """The guard must not have quietly turned the daily update into a no-op."""
    calls: dict = {}
    assert _run_update(monkeypatch, calls) == 0
    assert calls["import_mlb"] is True
