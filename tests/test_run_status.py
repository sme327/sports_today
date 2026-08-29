"""The run log's second half: proving a publish happened, and noticing when it didn't.

The daily run is two programs and the terminal's most success-looking line
("Data updated. Run ... to publish.") is printed *before* publishing starts. On
2026-08-28 the publish half then hung — no error, no exit code, no timeout — while the
site served the previous day's slate. Every check that existed read `site-dist/`, the
thing the build had just written, so all of them passed.

These tests cover the three states that failure could have been in, because they look
identical from the terminal and only the log tells them apart: it never started, it
started and never finished, or it finished before the data it was supposed to publish.
"""

from __future__ import annotations

import json

from scripts.run_log import PUBLISH_FINISHED, PUBLISH_STARTED, event_of, read_runs
from scripts.run_status import describe, latest


def data_run(at: str, **extra) -> dict:
    return {"run_at": at, "mlb": {"games": 2011, "plate_appearances": 157372}, **extra}


def started(at: str) -> dict:
    return {"run_at": at, "event": PUBLISH_STARTED}


def finished(at: str, ok: bool = True, **extra) -> dict:
    record = {"run_at": at, "event": PUBLISH_FINISHED, "ok": ok,
              "pages": 740, "build_stamp": "2026-08-28T15:53:10"}
    record.update(extra)
    return record


def report(records, live_stamp=None, live_error=None):
    lines, healthy = describe(records, live_stamp, live_error)
    return "\n".join(lines), healthy


# --- the log itself -------------------------------------------------------------

def test_records_written_before_the_publish_half_existed_read_as_data_runs():
    """Every line written before 2026-08-28 has no `event` key. They must not be
    mistaken for publishes, or an old log would look permanently healthy."""
    assert event_of({"run_at": "t", "mlb": {}}) == "data_run"
    assert event_of(started("t")) == PUBLISH_STARTED


def test_a_corrupt_final_line_does_not_hide_the_good_records(tmp_path):
    """A killed run is exactly what leaves a half-written line, and that is precisely
    when you most need to read the records above it."""
    log = tmp_path / "runs.jsonl"
    log.write_text(
        json.dumps(data_run("2026-08-28T15:51:41")) + "\n"
        + json.dumps(started("2026-08-28T15:55:33")) + "\n"
        + '{"run_at": "2026-08-2',  # truncated mid-write
        encoding="utf-8",
    )
    records = read_runs(log)
    assert len(records) == 2
    assert event_of(records[1]) == PUBLISH_STARTED


def test_latest_uses_write_order_not_timestamps(tmp_path):
    """Sorting on `run_at` would let a clock change outrank the actual sequence."""
    records = [finished("2026-08-28T18:00:00"), finished("2026-08-28T09:00:00")]
    assert latest(records, PUBLISH_FINISHED)["run_at"] == "2026-08-28T09:00:00"


# --- the three ways a publish goes missing ---------------------------------------

def test_a_publish_that_never_started_is_reported():
    text, healthy = report([data_run("2026-08-28T15:51:41")])
    assert not healthy
    assert "never recorded" in text


def test_a_publish_that_started_and_never_finished_is_called_out():
    """The 2026-08-28 hang. The build completed and the terminal showed no error, so
    the missing finish record is the only evidence that exists."""
    text, healthy = report([
        data_run("2026-08-28T15:51:41"),
        started("2026-08-28T15:55:33"),
    ])
    assert not healthy
    assert "NEVER FINISHED" in text


def test_a_finish_older_than_its_start_still_counts_as_hung():
    """Yesterday's successful publish must not satisfy today's start."""
    text, healthy = report([
        finished("2026-08-27T12:01:00"),
        data_run("2026-08-28T15:51:41"),
        started("2026-08-28T15:55:33"),
    ])
    assert not healthy
    assert "NEVER FINISHED" in text


def test_data_newer_than_the_last_successful_publish_means_the_site_is_behind():
    """Both halves succeeded, but in the wrong order — the site is a slate behind."""
    text, healthy = report([
        started("2026-08-27T11:52:00"),
        finished("2026-08-27T12:01:00"),
        data_run("2026-08-28T15:51:41"),
    ])
    assert not healthy
    assert "older slate" in text


def test_a_failed_deploy_reports_why():
    text, healthy = report([
        data_run("2026-08-28T15:51:41"),
        started("2026-08-28T15:55:33"),
        finished("2026-08-28T15:58:00", ok=False, deploy_exit=1),
    ])
    assert not healthy
    assert "FAILED" in text and "wrangler exited 1" in text


# --- the healthy case, and the live check ----------------------------------------

def test_a_complete_run_is_healthy_and_says_what_it_published():
    text, healthy = report([
        data_run("2026-08-28T15:51:41"),
        started("2026-08-28T15:55:33"),
        finished("2026-08-28T15:58:00", verified=True),
    ])
    assert healthy
    assert "OK" in text and "740 pages" in text and "verified live" in text
    assert "Fix:" not in text


def test_a_live_stamp_older_than_the_build_is_stale_even_when_the_run_succeeded():
    """The deploy reported success and the log agrees — but the origin serves something
    else. This is the check no local signal can make."""
    text, healthy = report([
        data_run("2026-08-28T15:51:41"),
        started("2026-08-28T15:55:33"),
        finished("2026-08-28T15:58:00", verified=True),
    ], live_stamp="2026-08-27T11:54:48")
    assert not healthy
    assert "STALE" in text


def test_a_matching_live_stamp_confirms_the_publish():
    text, healthy = report([
        data_run("2026-08-28T15:51:41"),
        started("2026-08-28T15:55:33"),
        finished("2026-08-28T15:58:00", verified=True),
    ], live_stamp="2026-08-28T15:53:10")
    assert healthy
    assert "matches the last publish" in text


def test_being_offline_is_not_reported_as_a_broken_publish():
    text, healthy = report([
        data_run("2026-08-28T15:51:41"),
        started("2026-08-28T15:55:33"),
        finished("2026-08-28T15:58:00", verified=True),
    ], live_error="[Errno 8] nodename nor servname provided")
    assert healthy
    assert "could not check" in text


# --- the publish half always records an outcome -----------------------------------

def _capture(monkeypatch):
    """Intercept the log writes `publish_pages.main` makes, without touching disk."""
    import scripts.publish_pages as pp

    written: list[dict] = []
    monkeypatch.setattr(pp, "append_run_log", lambda record: written.append(record))
    return pp, written


def test_a_crash_mid_publish_still_records_a_finish(monkeypatch):
    """Without this, a raised exception would leave a start and no finish — reported as
    a hang, which would send you looking for a stuck process that does not exist."""
    pp, written = _capture(monkeypatch)

    def boom(args, record):
        raise RuntimeError("wrangler vanished")

    monkeypatch.setattr(pp, "publish", boom)
    try:
        pp.main([])
    except RuntimeError:
        pass
    else:
        raise AssertionError("the exception must still reach the caller")

    assert [r["event"] for r in written] == [PUBLISH_STARTED, PUBLISH_FINISHED]
    assert written[1]["ok"] is False
    assert "wrangler vanished" in written[1]["error"]
    assert "duration_seconds" in written[1]


def test_a_cancelled_publish_records_a_finish_too(monkeypatch):
    """Ctrl-C is the operator's own doing, but it must not masquerade as a hang."""
    pp, written = _capture(monkeypatch)

    def cancel(args, record):
        raise KeyboardInterrupt

    monkeypatch.setattr(pp, "publish", cancel)
    try:
        pp.main([])
    except KeyboardInterrupt:
        pass

    assert [r["event"] for r in written] == [PUBLISH_STARTED, PUBLISH_FINISHED]
    assert written[1]["ok"] is False
    assert "KeyboardInterrupt" in written[1]["error"]


def test_build_only_records_nothing(monkeypatch):
    """`--build-only` never deploys, so it cannot leave the site stale and must not
    write a publish record that would later read as a successful publish."""
    pp, written = _capture(monkeypatch)
    monkeypatch.setattr(pp, "build_site", lambda: None)
    assert pp.main(["--build-only"]) == 0
    assert written == []
