"""The whole NFL season's schedule, so it can be browsed by week or by team.

**Why this is not `nfl_team_games`.** That table holds *played* games from the ingested
Big Data Ball seasons — it is the deep-dive's evidence base, it only ever contains
results, and it carries the vendor's own team naming. This holds the **forward**
schedule for the current season, from ESPN, which is a different question asked of a
different source. Joining them would mean reconciling two id spaces to answer a question
neither needs the other for, so they stay apart.

**Why a table rather than a live fetch.** The site is a static export. Browsing by week
and by team is ~50 pages, and fetching per page would turn one build into fifty network
calls. The season schedule changes rarely — flexed games move a kickoff, not a matchup —
so one collection per daily run is ample.

Description only, like everything else here: this is where and when games are played.
It makes no claim about who wins.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.config import DB_PATH
from src.ncaaf_collector import fetch_json

TABLE = "nfl_schedule"
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
REGULAR_SEASON_WEEKS = 18

COLUMNS = (
    "season", "week", "game_id", "start_time", "venue",
    "away_id", "away_name", "away_abbr", "away_logo",
    "home_id", "home_name", "home_abbr", "home_logo",
    "status", "away_score", "home_score", "collected_at",
)


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            season INTEGER NOT NULL,
            week INTEGER NOT NULL,
            game_id TEXT NOT NULL,
            start_time TEXT,
            venue TEXT,
            away_id TEXT, away_name TEXT, away_abbr TEXT, away_logo TEXT,
            home_id TEXT, home_name TEXT, home_abbr TEXT, home_logo TEXT,
            status TEXT,
            away_score INTEGER,
            home_score INTEGER,
            collected_at TEXT,
            PRIMARY KEY (season, game_id)
        )
        """
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_week ON {TABLE} (season, week)")


def upsert(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    placeholders = ", ".join("?" for _ in COLUMNS)
    conn.executemany(
        f"INSERT OR REPLACE INTO {TABLE} ({', '.join(COLUMNS)}) VALUES ({placeholders})",
        [tuple(r.get(c) for c in COLUMNS) for r in rows])
    return len(rows)


def _side(competitors: list, home_away: str) -> dict:
    for c in competitors:
        if c.get("homeAway") == home_away:
            return c
    return {}


def week_rows(season: int, week: int) -> list[dict]:
    payload = fetch_json(f"{SCOREBOARD}?seasontype=2&week={week}&dates={season}")
    if not payload:
        return []
    collected = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for event in payload.get("events") or []:
        comp = (event.get("competitions") or [{}])[0]
        competitors = comp.get("competitors") or []
        away, home = _side(competitors, "away"), _side(competitors, "home")
        at, ht = away.get("team") or {}, home.get("team") or {}
        if not at or not ht:
            continue

        def _score(side):
            try:
                return int(side.get("score"))
            except (TypeError, ValueError):
                return None

        rows.append({
            "season": season, "week": week, "game_id": str(event.get("id") or ""),
            "start_time": event.get("date"),
            "venue": (comp.get("venue") or {}).get("fullName"),
            "away_id": str(at.get("id") or ""), "away_name": at.get("displayName"),
            "away_abbr": at.get("abbreviation"), "away_logo": at.get("logo"),
            "home_id": str(ht.get("id") or ""), "home_name": ht.get("displayName"),
            "home_abbr": ht.get("abbreviation"), "home_logo": ht.get("logo"),
            "status": ((event.get("status") or {}).get("type") or {}).get("state"),
            "away_score": _score(away), "home_score": _score(home),
            "collected_at": collected,
        })
    return rows


def collect(season: int, db_path: Path = DB_PATH) -> int:
    """Fetch every regular-season week. Non-fatal per week: a schedule missing week 12
    is better than a daily run that fails because one request timed out."""
    written = 0
    with sqlite3.connect(db_path) as conn:
        ensure_tables(conn)
        for week in range(1, REGULAR_SEASON_WEEKS + 1):
            try:
                rows = week_rows(season, week)
            except Exception:
                continue
            written += upsert(conn, rows)
        conn.commit()
    return written


def load(season: int, db_path: Path = DB_PATH) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"SELECT * FROM {TABLE} WHERE season = ? ORDER BY week, start_time",
                (season,)).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(r) for r in rows]


def seasons(db_path: Path = DB_PATH) -> list[int]:
    with sqlite3.connect(db_path) as conn:
        try:
            return [int(r[0]) for r in conn.execute(
                f"SELECT DISTINCT season FROM {TABLE} ORDER BY season DESC")]
        except sqlite3.OperationalError:
            return []
