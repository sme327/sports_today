"""Import Big Data Ball box-score workbooks (NBA / CBB / WNBA / MLB) into SQLite.

    python -m scripts.import_boxscore_feed --sport nba --player <x.xlsx> --team <y.xlsx>
    python -m scripts.import_boxscore_feed --sport cbb --all <gamelogs.xlsx>

``--all`` reads whichever of the player/team/DNP sheets a single workbook happens to
contain, which is how the consolidated multi-season archives ship.

**Not part of the daily loop.** Like the NFL import, this is run by hand when a season
lands. Writes are additive per season, so loading one year leaves the others in place.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.boxscore_ingest import SPORTS, import_feed, pick_sheet
from src.config import DB_PATH


def _try(path: Path, sport: str, kind: str, db: Path, required: bool,
         force: bool = False) -> int:
    try:
        pick_sheet(path, kind)
    except KeyError:
        if required:
            print(f"  {kind:<7} no matching sheet in {path.name}", file=sys.stderr)
        return 0
    try:
        r = import_feed(path, sport, kind, db, force=force)
    except Exception as exc:                                   # noqa: BLE001
        print(f"  {kind:<7} FAILED — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0
    for season, (have, incoming) in sorted(r.get("skipped", {}).items()):
        print(f"  {kind:<7} kept {season} as-is — stored {have} games, this file has "
              f"{incoming}. Use --force to overwrite.")
    if not r["rows"]:
        return 0
    lo, hi = r["date_range"]
    seasons = ", ".join(str(s) for s in r["seasons"])
    print(f"  {kind:<7} -> {r['table']:<22} {r['rows']:>8,} rows  {r['games']:>6,} games  "
          f"{r['columns']:>3} cols  {lo} to {hi}  [{seasons}]")
    if not r.get("joinable", True):
        print(f"  {'':<7}    ! no game id in this vintage — rows are stored but cannot be "
              f"joined to a game (we never join on names)")
    return r["rows"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sport", required=True, choices=sorted(SPORTS),
                   help="which sport's calendar and table prefix to use")
    p.add_argument("--player", type=Path, help="workbook holding player rows")
    p.add_argument("--team", type=Path, help="workbook holding team rows")
    p.add_argument("--all", type=Path, dest="every",
                   help="one workbook — read every sheet kind it contains")
    p.add_argument("--db", type=Path, default=DB_PATH)
    p.add_argument("--force", action="store_true",
                   help="overwrite a season even if this file has fewer games than stored")
    args = p.parse_args(argv)

    if not any((args.player, args.team, args.every)):
        p.error("pass at least one of --player / --team / --all")

    total = 0
    for path, kinds, required in ((args.every, ("team", "player", "dnp"), False),
                                  (args.player, ("player", "dnp"), True),
                                  (args.team, ("team",), True)):
        if not path:
            continue
        if not path.exists():
            print(f"Missing: {path}", file=sys.stderr)
            return 1
        print(f"{path.name}")
        for kind in kinds:
            total += _try(path, args.sport, kind, args.db,
                          required and kind != "dnp", args.force)
    print(f"\n{total:,} rows written to {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
