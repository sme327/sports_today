from __future__ import annotations

import sqlite3
from pathlib import Path

from src.config import DB_PATH


def main() -> int:
    with sqlite3.connect(DB_PATH) as conn:
        teams = conn.execute(
            """
            SELECT batting_team FROM plate_appearances
            UNION
            SELECT pitching_team FROM plate_appearances
            ORDER BY 1
            """
        ).fetchall()
        games = conn.execute(
            "SELECT COUNT(DISTINCT game_id) FROM plate_appearances"
        ).fetchone()[0]

    team_names = [row[0] for row in teams]
    print(f"Distinct games: {games:,}")
    print(f"Distinct teams: {len(team_names):,}")
    for team in team_names:
        print(f" - {team}")

    if len(team_names) < 20:
        print(
            "\nWARNING: This does not look like a full MLB season feed. "
            "Opportunity analysis will only work for scheduled teams present "
            "in this database."
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
