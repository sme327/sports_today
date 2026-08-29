"""Did today's run actually finish — data *and* publish?

The daily run is two programs. `morning_update` ends by printing a line telling you to
run `publish_pages`, and it prints that before publishing starts, so the most
success-looking line in the terminal is the halfway mark. On 2026-08-28 the publish
half then hung, and every local signal stayed healthy while the site served the
previous day's slate.

This reads `logs/update_runs.jsonl` and answers the question the terminal cannot:

    python -m scripts.run_status

Exit code is 0 when the slate on the site matches the slate in the database, and 1 when
it does not — so it can gate a script as well as inform a person.
"""

from __future__ import annotations

import argparse
import sys

from scripts.run_log import (
    DATA_RUN,
    PUBLISH_FINISHED,
    PUBLISH_STARTED,
    RUN_LOG,
    event_of,
    read_runs,
)

LIVE_URL = "https://sports.sme327.com/"


def latest(records: list[dict], event: str) -> dict | None:
    """Records are appended in order, so the last match is the newest. Sorting on
    `run_at` instead would rank a clock change above write order."""
    for record in reversed(records):
        if event_of(record) == event:
            return record
    return None


def fetch_live_stamp(url: str, timeout: float = 10.0) -> tuple[str | None, str | None]:
    """(stamp, error). Never raises: this is the one check that needs the network, and
    being offline must not look like a broken publish."""
    import urllib.error
    import urllib.request
    from time import time

    from scripts.publish_pages import build_stamp

    context = None
    try:
        import ssl

        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    probe = url + ("&" if "?" in url else "?") + f"cb={int(time())}"
    request = urllib.request.Request(probe, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Cache-Control": "no-cache",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as resp:
            return build_stamp(resp.read().decode("utf-8", "replace")), None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, str(exc)


def describe(records: list[dict], live_stamp: str | None,
             live_error: str | None) -> tuple[list[str], bool]:
    """(lines to print, healthy)."""
    lines: list[str] = []
    healthy = True

    data = latest(records, DATA_RUN)
    started = latest(records, PUBLISH_STARTED)
    finished = latest(records, PUBLISH_FINISHED)

    if data is None:
        return ["No update run has ever been recorded."], False

    lines.append(f"Data     {data.get('run_at', '?')}")
    mlb = data.get("mlb") or {}
    if mlb:
        lines.append(f"         {mlb.get('games', '?'):,} games, "
                     f"{mlb.get('plate_appearances', 0):,} plate appearances")
    for slate in data.get("daily_feed") or []:
        lines.append(f"         {slate.get('date')}: {slate.get('games', '?')} games, "
                     f"{slate.get('opportunities', '?')} opportunities")
    if data.get("error"):
        lines.append(f"         FAILED: {data['error']}")
        healthy = False

    lines.append("")

    if finished is None and started is None:
        lines.append("Publish  never recorded")
        lines.append("         The site has not been published since this log began.")
        return lines + _hint(), False

    # A start with no finish after it is the signature of a hang: the process died or
    # is still sitting there, and a process that never returns cannot log its own end.
    hung = started is not None and (
        finished is None or finished.get("run_at", "") < started.get("run_at", ""))
    if hung:
        lines.append(f"Publish  STARTED {started.get('run_at', '?')} — NEVER FINISHED")
        lines.append("         Either it is still running, or it hung and was killed.")
        lines.append("         The built pages may be complete while the site is stale.")
        return lines + _hint(), False

    assert finished is not None
    if finished.get("ok"):
        detail = f"{finished.get('pages', '?')} pages"
        if finished.get("build_stamp"):
            detail += f", build {finished['build_stamp']}"
        if finished.get("verified"):
            detail += ", verified live"
        lines.append(f"Publish  {finished.get('run_at', '?')}  OK — {detail}")
    else:
        healthy = False
        why = finished.get("error") or f"wrangler exited {finished.get('deploy_exit')}"
        lines.append(f"Publish  {finished.get('run_at', '?')}  FAILED — {why}")

    # The decisive comparison: is the newest data actually on the site? A publish that
    # succeeded before the last data run left the site a slate behind.
    if finished.get("run_at", "") < data.get("run_at", ""):
        healthy = False
        lines.append("")
        lines.append("         The data was updated AFTER the last successful publish.")
        lines.append("         The site is serving an older slate.")

    if live_error:
        lines.append("")
        lines.append(f"Live     could not check ({live_error})")
    elif live_stamp is not None:
        lines.append("")
        expected = finished.get("build_stamp")
        if expected and live_stamp != expected:
            healthy = False
            lines.append(f"Live     {live_stamp}  STALE — expected {expected}")
        else:
            lines.append(f"Live     {live_stamp}  matches the last publish")

    return (lines if healthy else lines + _hint()), healthy


def _hint() -> list[str]:
    return ["", "Fix: python -m scripts.publish_pages"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-live", action="store_true",
                        help="Skip the live-site check (no network).")
    parser.add_argument("--url", default=LIVE_URL)
    args = parser.parse_args(argv)

    records = read_runs()
    if not records:
        print(f"No run log at {RUN_LOG}.", file=sys.stderr)
        return 1

    live_stamp, live_error = (None, None)
    if not args.no_live:
        live_stamp, live_error = fetch_live_stamp(args.url)

    lines, healthy = describe(records, live_stamp, live_error)
    print("\n".join(lines))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
