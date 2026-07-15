from __future__ import annotations

import sqlite3

from src.config import DB_PATH


def main() -> int:
    with sqlite3.connect(DB_PATH) as conn:
        games = conn.execute(
            "SELECT COUNT(DISTINCT game_id) FROM wnba_player_game_logs"
        ).fetchone()[0]
        players = conn.execute(
            "SELECT COUNT(DISTINCT player_id) FROM wnba_player_game_logs"
        ).fetchone()[0]
        teams = conn.execute(
            "SELECT COUNT(DISTINCT team_id) FROM wnba_player_game_logs"
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT COUNT(*) FROM wnba_player_game_logs"
        ).fetchone()[0]
        date_range = conn.execute(
            "SELECT MIN(game_date), MAX(game_date) FROM wnba_player_game_logs"
        ).fetchone()

    print(f"Player-game rows: {rows:,}")
    print(f"Games: {games:,}")
    print(f"Players: {players:,}")
    print(f"Teams: {teams:,}")
    print(f"Date range: {date_range[0]} through {date_range[1]}")
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
