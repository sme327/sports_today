from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from scripts.sync_mlb_download import sync_latest
from services.update_pipeline import rebuild
from src.config import CURRENT_FEED, DOWNLOADS_DIR


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
        help="Update data and database without launching Streamlit.",
    )
    args = parser.parse_args()

    try:
        current_file, changed = sync_latest(args.downloads, force=args.force)
        print(f"Using feed: {current_file}")

        # One shared pipeline for the CLI and the in-app uploader: import the MLB
        # feed, refresh WNBA + MLS, publish the DB to the cloud store (if configured).
        result = rebuild(CURRENT_FEED)
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
        for iso, g in (result.get("regraded") or {}).items():
            print(f"Re-graded {iso}: {g['hit']} hit, {g['miss']} miss, {g['void']} void.")
        if result.get("published"):
            print("Published database to the cloud store.")

        if not args.no_launch:
            print("Launching Sports Today...")
            return subprocess.call(
                [sys.executable, "-m", "streamlit", "run", "app.py"]
            )
        return 0
    except KeyboardInterrupt:
        print("\nUpdate cancelled.")
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
