from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from scripts.sync_mlb_download import sync_latest
from services.update_pipeline import rebuild
from src.config import CURRENT_FEED, DOWNLOADS_DIR, LOG_DIR

RUN_LOG = LOG_DIR / "update_runs.jsonl"


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the full MLB morning update: locate the newest feed in Downloads, "
            "archive/copy it, rebuild SQLite, and optionally launch Sports Today."
        )
    )
    parser.add_argument(
        "--downloads",
        type=Path,
        default=DOWNLOADS_DIR,
        help="Downloads directory to search. Defaults to ~/Downloads.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force copying the newest workbook even if unchanged.",
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Kept for compatibility; nothing is launched either way.",
    )
    args = parser.parse_args()

    try:
        current_file, changed = sync_latest(args.downloads, force=args.force)
        print(f"Using feed: {current_file}")

        # One shared pipeline: import the MLB feed, refresh WNBA + MLS (+ NFL pickup),
        # regrade, precompute, publish the DB to the cloud store (if configured).
        started = datetime.now()
        result = rebuild(CURRENT_FEED)
        log_error = append_run_log({
            "run_at": started.isoformat(timespec="seconds"),
            "duration_seconds": round((datetime.now() - started).total_seconds(), 1),
            "feed": str(current_file),
            "feed_changed": changed,
            **result,
        })
        if log_error:
            print(f"Run log not written: {log_error}", file=sys.stderr)
        s = result["mlb"]
        print(
            "Database rebuilt successfully: "
            f"{s['plate_appearances']:,} plate appearances, "
            f"{s['games']:,} games, {s['batters']:,} batters, {s['pitchers']:,} pitchers."
        )
        if "wnba" in result:
            print(f"WNBA updated: {result['wnba']['games']:,} new games, "
                  f"{result['wnba']['rows']:,} player rows.")
        elif "wnba_error" in result:
            print(f"WNBA update skipped: {result['wnba_error']}", file=sys.stderr)
        if "mls" in result:
            print(f"MLS updated: {result['mls']['matches']:,} new matches, "
                  f"{result['mls']['standings']:,} standings rows.")
        elif "mls_error" in result:
            print(f"MLS update skipped: {result['mls_error']}", file=sys.stderr)
        if "nfl" in result:
            print(result["nfl"]["message"])
        elif "nfl_error" in result:
            print(f"NFL feed refresh skipped: {result['nfl_error']}", file=sys.stderr)
        if result.get("game_outcomes"):
            print(f"Game outcomes recorded: {result['game_outcomes']} finished games "
                  f"(feeds the editorial calibration).")
        elif "game_outcomes_error" in result:
            print(f"Game outcomes skipped: {result['game_outcomes_error']}", file=sys.stderr)
        for feed in result.get("daily_feed", []):
            print(
                f"Daily feed {feed['date']}: {feed['games']} games, "
                f"{feed['opportunities']} opportunities, {feed.get('matchup_pages', 0)} "
                f"matchup pages in {feed['total_seconds']:.1f}s."
            )
            for detail in feed.get("matchup_error_details", []):
                print(f"  Matchup page failed: {detail}", file=sys.stderr)
        if "daily_feed_error" in result:
            print(f"Daily feed precompute skipped: {result['daily_feed_error']}", file=sys.stderr)
        for iso, g in (result.get("regraded") or {}).items():
            print(f"Re-graded {iso}: {g['hit']} hit, {g['miss']} miss, {g['void']} void.")
        # A conservative segment scan is useful monthly, not daily. It is non-fatal:
        # publishing current sports data must never depend on an analytical report.
        try:
            from scripts.signal_discovery import write_report
            signal_path = write_report()
            if signal_path:
                print(f"Signal discovery report written: {signal_path}")
        except Exception as exc:
            print(f"Signal discovery report skipped: {exc}", file=sys.stderr)
        if result.get("published"):
            print("Published database to the cloud store.")

        if not args.no_launch:
            # The Streamlit app retired 2026-08-17; the site is published rather than
            # launched. `update_and_publish.command` runs this then scripts.publish_pages.
            print("Data updated. Run `python -m scripts.publish_pages` to publish.")
        return 0
    except KeyboardInterrupt:
        print("\nUpdate cancelled.")
        return 130
    except Exception as exc:
        append_run_log({
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "error": str(exc),
        })
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
