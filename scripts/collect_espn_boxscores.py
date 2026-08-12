"""Collect ESPN player box scores for a sport and date range.

    python -m scripts.collect_espn_boxscores --sport nba --start 2025-10-21 --end 2026-06-13
    python -m scripts.collect_espn_boxscores --sport nhl --days 7        # recent catch-up

Incremental: games already holding player rows are skipped, so re-running is cheap and
safe. Backfill volume is roughly 1,300 games a season for NBA and NHL, ~6,300 for CBB.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from src.config import DB_PATH
from src.espn_boxscore import SPORTS, collect


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sport", required=True, choices=sorted(SPORTS))
    p.add_argument("--start", type=date.fromisoformat)
    p.add_argument("--end", type=date.fromisoformat)
    p.add_argument("--days", type=int, help="collect the last N days instead of a range")
    p.add_argument("--db", default=DB_PATH)
    p.add_argument("--force", action="store_true", help="re-download games already held")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.days:
        end = date.today()
        start = end - timedelta(days=args.days)
    elif args.start and args.end:
        start, end = args.start, args.end
    else:
        p.error("pass --days, or both --start and --end")

    spec = SPORTS[args.sport]
    print(f"{spec.label}: {start} to {end}")
    r = collect(args.sport, start, end, args.db, force=args.force,
                progress=not args.quiet)
    print(f"\n  games seen        {r.games_seen:,}")
    print(f"  completed         {r.completed_games:,}")
    print(f"  downloaded        {r.games_downloaded:,}")
    print(f"  player rows       {r.player_rows:,}")
    print(f"  skipped (held)    {r.skipped_existing:,}")
    if r.failures:
        print(f"  failures          {len(r.failures)}")
        for f in r.failures[:5]:
            print(f"    - {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
