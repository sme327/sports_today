"""Import the NFL season feeds (Big Data Ball team + player xlsx) into Sports Today
SQLite. Full-season replace, like the MLB import.

    python -m scripts.import_nfl_feed --team <team.xlsx> --player <player.xlsx>

With no arguments it looks for the newest ``*nfl-season-team-feed.xlsx`` /
``*nfl-season-player-feed.xlsx`` pair in ~/Downloads, then ~/Documents.
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

from src.config import DB_PATH
from src.nfl_ingest import import_nfl_feeds

_SEARCH_DIRS = [Path.home() / "Downloads", Path.home() / "Documents"]


def _newest(pattern: str) -> Path | None:
    hits: list[str] = []
    for d in _SEARCH_DIRS:
        hits += glob.glob(str(d / "**" / pattern), recursive=True)
    return Path(max(hits, key=lambda p: Path(p).stat().st_mtime)) if hits else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Import NFL season feeds into Sports Today.")
    parser.add_argument("--team", type=Path, default=None, help="team-feed .xlsx")
    parser.add_argument("--player", type=Path, default=None, help="player-feed .xlsx")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()

    team = args.team or _newest("*nfl-season-team-feed.xlsx")
    player = args.player or _newest("*nfl-season-player-feed.xlsx")
    if not team or not player:
        print("Could not find both NFL feeds. Pass --team and --player.", file=sys.stderr)
        return 1

    print(f"Team feed:   {team}")
    print(f"Player feed: {player}")
    counts = import_nfl_feeds(team, player, args.db)
    seasons = ", ".join(str(s) for s in counts["seasons"])
    print(f"Imported {counts['team_games']} team-game rows and {counts['player_games']:,} "
          f"player-game rows across {counts['games']} games (through week {counts['weeks']}), "
          f"{counts['teams']} teams — season {seasons}. Other loaded seasons are kept.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
