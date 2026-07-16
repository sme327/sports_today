"""Sports Today data diagnostics (CLI only — never part of UI rendering).

Reports MLB and WNBA data coverage and whether stored data looks complete.
Supersedes the old validate_mlb_feed.py / validate_wnba_data.py scripts.

    python diagnostics.py
"""

from __future__ import annotations

import sqlite3

from src.config import DB_PATH
from services.data_access import table_exists


def _report_mlb(conn: sqlite3.Connection) -> bool:
    if not table_exists(conn, "plate_appearances"):
        print("MLB: plate_appearances table missing.")
        return False
    games = conn.execute("SELECT COUNT(DISTINCT game_id) FROM plate_appearances").fetchone()[0]
    players = conn.execute("SELECT COUNT(DISTINCT batter_id) FROM plate_appearances").fetchone()[0]
    lo, hi = conn.execute("SELECT MIN(game_date), MAX(game_date) FROM plate_appearances").fetchone()
    teams = conn.execute(
        "SELECT COUNT(*) FROM (SELECT batting_team FROM plate_appearances "
        "UNION SELECT pitching_team FROM plate_appearances)"
    ).fetchone()[0]
    print("MLB")
    print(f"  teams: {teams}")
    print(f"  games: {games:,}")
    print(f"  batters: {players:,}")
    print(f"  date range: {lo} -> {hi}")
    if teams < 20:
        print("  WARNING: fewer than 20 teams — likely not a full-season feed.")
        return False
    return True


def _report_wnba(conn: sqlite3.Connection) -> bool:
    if not table_exists(conn, "wnba_player_game_logs"):
        print("WNBA: wnba_player_game_logs table missing.")
        return False
    rows = conn.execute("SELECT COUNT(*) FROM wnba_player_game_logs").fetchone()[0]
    games = conn.execute("SELECT COUNT(DISTINCT game_id) FROM wnba_player_game_logs").fetchone()[0]
    players = conn.execute("SELECT COUNT(DISTINCT player_id) FROM wnba_player_game_logs").fetchone()[0]
    teams = conn.execute("SELECT COUNT(DISTINCT team_id) FROM wnba_player_game_logs").fetchone()[0]
    lo, hi = conn.execute("SELECT MIN(game_date), MAX(game_date) FROM wnba_player_game_logs").fetchone()
    print("WNBA")
    print(f"  teams: {teams}")
    print(f"  games: {games:,}")
    print(f"  players: {players:,}")
    print(f"  player-game rows: {rows:,}")
    print(f"  date range: {lo} -> {hi}")
    return rows > 0


def main() -> int:
    if not DB_PATH.exists():
        print(f"No database at {DB_PATH}. Run update.command first.")
        return 2
    with sqlite3.connect(DB_PATH) as conn:
        ok_mlb = _report_mlb(conn)
        print()
        ok_wnba = _report_wnba(conn)
    return 0 if (ok_mlb and ok_wnba) else 2


if __name__ == "__main__":
    raise SystemExit(main())
