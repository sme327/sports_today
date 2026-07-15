from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from src.wnba_collector import collect_wnba_season


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Dates must use YYYY-MM-DD."
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Collect WNBA schedule and completed player game logs into "
            "Sports Hub SQLite and CSV exports."
        )
    )
    parser.add_argument("--season", type=int, default=date.today().year)
    parser.add_argument("--start", type=parse_date)
    parser.add_argument("--end", type=parse_date, default=date.today())
    parser.add_argument(
        "--force",
        action="store_true",
        help="Redownload completed games already stored locally.",
    )
    parser.add_argument(
        "--include-today-incomplete",
        action="store_true",
        help="Attempt current-day box scores even when a game is not final.",
    )
    args = parser.parse_args()

    result = collect_wnba_season(
        season=args.season,
        start_date=args.start,
        end_date=args.end,
        force=args.force,
        include_today_incomplete=args.include_today_incomplete,
    )

    print("WNBA collection complete")
    print(f"Games seen: {result.games_seen:,}")
    print(f"Completed games: {result.completed_games:,}")
    print(f"Games downloaded: {result.games_downloaded:,}")
    print(f"Existing games skipped: {result.skipped_existing_games:,}")
    print(f"Player rows written: {result.player_rows_written:,}")
    print(f"Database: {result.database_path}")
    print(f"Games CSV: {result.games_csv}")
    print(f"Player logs CSV: {result.player_logs_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
