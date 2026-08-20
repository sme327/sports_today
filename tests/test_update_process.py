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
