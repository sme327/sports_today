from __future__ import annotations

import argparse
from pathlib import Path

from src.config import CURRENT_FEED
from src.ingest import import_feed


def main() -> int:
    parser = argparse.ArgumentParser(description="Import an MLB PBP workbook into Sports Hub SQLite.")
    parser.add_argument(
        "workbook",
        nargs="?",
        type=Path,
        default=CURRENT_FEED,
        help="Workbook path. Defaults to data/current/mlb_pbp_current.xlsx.",
    )
    args = parser.parse_args()

    db, summary = import_feed(args.workbook)
    print(f"Database: {db}")
    for key, value in summary.items():
        print(f"{key}: {value:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
