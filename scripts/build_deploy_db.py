"""Build a slim copy of the database for deployment.

The working database carries research tables nothing in the app reads — ingested NBA/CBB
box scores, collector output, MLB box scores. They are ~86% of the rows and are there so a
future feature starts with data in SQLite rather than a spreadsheet. **None of it belongs
on a phone.**

A deployed copy is downloaded on cold boot and re-uploaded after each daily update, so its
size is paid on every one of those. Stripping the research tables takes the file from
~304MB to a fraction of that with **no change to anything a reader sees**.

    python -m scripts.build_deploy_db                 # writes database/sportshub-deploy.db
    python -m scripts.build_deploy_db --check         # report sizes, write nothing

**Allow-list, not deny-list.** A new research table added later is excluded by default,
which is the safe direction: shipping a table nobody reads costs bandwidth, while dropping
one somebody does breaks a page. Anything genuinely user-facing has to be named here, and
`--check` fails loudly if a listed table has gone missing.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

from src.config import DB_PATH

# Everything a running app reads. Grouped by what it serves so the reason is visible.
KEEP: dict[str, tuple[str, ...]] = {
    "MLB (daily feed + scorers)": ("plate_appearances", "players", "games"),
    "WNBA (collector + scorers)": ("wnba_games", "wnba_player_game_logs",
                                   "wnba_collection_runs"),
    "MLS (collector + matchup page)": ("mls_matches", "mls_match_events", "mls_standings",
                                       "mls_team_match_stats", "mls_collection_runs"),
    "NFL (season archive + bridge)": ("nfl_team_games", "nfl_player_games", "nfl_teams",
                                      "nfl_feed_runs"),
    "results, grading, editorial": ("opportunity_snapshots", "game_outcomes"),
    "infrastructure": ("schedule_cache", "daily_opportunity_feed", "matchup_page_cache",
                       "schema_version", "sqlite_sequence"),
}

# Named only so `--check` can explain what it is dropping and why, rather than listing a
# table the reader has to go and look up.
RESEARCH_PREFIXES = ("cbb_", "nba_", "nhl_", "mlb_box_", "wnba_box_")


def _keep_set() -> set[str]:
    return {t for group in KEEP.values() for t in group}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _row_counts(conn: sqlite3.Connection, tables) -> dict[str, int]:
    out = {}
    for t in tables:
        try:
            out[t] = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        except sqlite3.OperationalError:
            out[t] = 0
    return out


def report(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        present = _tables(conn)
        counts = _row_counts(conn, present)
    keep = _keep_set()
    missing = sorted(keep - present - {"sqlite_sequence"})
    drop = sorted(present - keep)
    kept_rows = sum(counts[t] for t in present & keep)
    drop_rows = sum(counts[t] for t in drop)
    print(f"source: {db_path}  ({db_path.stat().st_size / 1e6:.0f} MB)\n")
    for group, tables in KEEP.items():
        here = [t for t in tables if t in present]
        print(f"  keep — {group}")
        for t in here:
            print(f"      {t:<28}{counts[t]:>10,}")
    if drop:
        print("\n  drop — not read by the app (research/collector data)")
        for t in drop:
            why = "research" if t.startswith(RESEARCH_PREFIXES) else "unused"
            print(f"      {t:<28}{counts[t]:>10,}   {why}")
    total = kept_rows + drop_rows
    print(f"\n  rows: {total:,} -> {kept_rows:,} ({kept_rows / total:.0%} kept)")
    if missing:
        print(f"\n  WARNING: expected tables absent from the source: {', '.join(missing)}",
              file=sys.stderr)
        return 1
    return 0


def build(db_path: Path, out_path: Path) -> Path:
    """Copy the database, drop everything not on the allow-list, and compact it."""
    if out_path.exists():
        out_path.unlink()
    shutil.copy2(db_path, out_path)
    keep = _keep_set()
    with sqlite3.connect(out_path) as conn:
        for table in sorted(_tables(conn) - keep):
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.commit()
        # VACUUM reclaims the pages the dropped tables held; without it the file stays
        # the same size on disk and the whole exercise is pointless.
        conn.isolation_level = None
        conn.execute("VACUUM")
    return out_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", type=Path, default=DB_PATH)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--check", action="store_true", help="report only; write nothing")
    args = p.parse_args(argv)

    if not args.db.exists():
        print(f"No database at {args.db}", file=sys.stderr)
        return 1
    rc = report(args.db)
    if args.check or rc:
        return rc
    out = args.out or args.db.with_name("sportshub-deploy.db")
    build(args.db, out)
    before, after = args.db.stat().st_size, out.stat().st_size
    print(f"\nwrote {out}")
    print(f"  {before / 1e6:.0f} MB -> {after / 1e6:.0f} MB  ({1 - after / before:.0%} smaller)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
