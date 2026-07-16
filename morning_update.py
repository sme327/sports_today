from __future__ import annotations

import argparse
from datetime import date
import subprocess
import sys
from pathlib import Path

from scripts.sync_mlb_download import sync_latest
from src.config import CURRENT_FEED, DOWNLOADS_DIR
from src.ingest import import_feed
from src.wnba_collector import collect_wnba_season


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

        db_path, summary = import_feed(CURRENT_FEED)
        print(
            "Database rebuilt successfully: "
            f"{summary['plate_appearances']:,} plate appearances, "
            f"{summary['games']:,} games, "
            f"{summary['batters']:,} batters, "
            f"{summary['pitchers']:,} pitchers."
        )

        try:
            wnba_result = collect_wnba_season(
                season=date.today().year,
                end_date=date.today(),
            )
            print(
                "WNBA updated: "
                f"{wnba_result.games_downloaded:,} new games, "
                f"{wnba_result.player_rows_written:,} player rows."
            )
        except Exception as exc:
            print(f"WNBA update skipped: {exc}", file=sys.stderr)

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
