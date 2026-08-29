"""The daily run's persisted record: one JSON line per event in `logs/update_runs.jsonl`.

Split out of `morning_update` so `publish_pages` can write here too without importing
the data pipeline (and its pandas/SQLite weight) just to append a line.

**Why the publish half writes a *pair* of records.** A failed deploy reports itself —
wrangler exits non-zero and the run says so. A *hung* deploy reports nothing at all:
on 2026-08-28 npm stopped on an `Ok to proceed?` prompt with the build already
complete, and the process sat there with no error, no timeout and no exit code while
the site served the previous day's slate. A process that never finishes cannot write
its own obituary, so the only way the log can show a hang is for the start to be
recorded separately from the finish. A `publish_started` with no matching
`publish_finished` *is* the evidence.

Record shapes (all carry `run_at`; `event` is absent on the data-half record, so
every line written before 2026-08-28 still reads correctly):

    {"run_at": ..., "mlb": {...}, "daily_feed": [...]}       the data half
    {"run_at": ..., "event": "publish_started"}
    {"run_at": ..., "event": "publish_finished", "ok": bool, ...}
"""

from __future__ import annotations

import json
from pathlib import Path

from src.config import LOG_DIR

RUN_LOG = LOG_DIR / "update_runs.jsonl"

DATA_RUN = "data_run"
PUBLISH_STARTED = "publish_started"
PUBLISH_FINISHED = "publish_finished"


def append_run_log(record: dict, path: Path = RUN_LOG) -> str | None:
    """One JSON line per update run, so "did Tuesday's update actually work?" is
    answerable after the terminal window closed. The import-history CSV records only
    the file copy; this records the whole rebuild summary — collectors, regrades,
    precompute, matchup-page failures and all. Returns an error string instead of
    raising: the record must never fail the update it records."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
        return None
    except Exception as exc:
        return str(exc)


def read_runs(path: Path = RUN_LOG) -> list[dict]:
    """Every record, oldest first. A truncated or corrupt line is skipped rather than
    raising: this log is diagnostic, and a half-written final line (the exact thing a
    killed run leaves behind) must not stop you reading the 200 good records above it.
    """
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def event_of(record: dict) -> str:
    """Records written before the publish half was logged carry no `event` key; they
    are all data runs."""
    return record.get("event") or DATA_RUN
