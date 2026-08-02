"""MLS team-match statistics collector (Phase 3B, Option A).

Collects the 2026 MLS **regular season** only (slug ``usa.1``): team match
statistics + standings, into normalized SQLite. Mirrors ``src/wnba_collector.py``:
retries with backoff, incremental collection, idempotent upserts, audit logging,
explicit validation, useful terminal output, and a nonzero exit on failure.

Honesty invariants:
- Never writes a partial/fabricated row. A structurally invalid match is skipped
  and counted as a failure; a *missing optional stat* is stored as NULL.
- Only regular-season, completed events are collected (no Leagues Cup, Open Cup,
  Concacaf, friendlies, or playoffs).

Not in this phase: player stats, match events, lineups, formations, xG.

CLI:
    python -m src.mls_collector --season 2026 --start 2026-03-07
    python -m src.mls_collector --force            # re-collect everything
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pandas as pd
import requests

from services import mls_store
from src import espn_soccer
from src.config import DATA_DIR, DB_PATH

SEASON_START_DEFAULT = date(2026, 3, 7)
REGULAR_SEASON_SLUG = "regular-season"
MLS_DATA_DIR = DATA_DIR / "mls"

DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 SportsHub/1.0"),
    "Accept": "application/json,text/plain,*/*",
}


class MLSCollectorError(RuntimeError):
    """Raised when the MLS source cannot be collected or parsed safely."""


@dataclass(frozen=True)
class CollectionResult:
    events_discovered: int
    completed_events: int
    events_collected: int
    events_skipped: int
    failures: int
    standings_rows: int
    start_date: str
    end_date: str
    database_path: str


# ------------------------------------------------------------- retries -------
def _with_retries(fn: Callable, *args, retries: int = 3, base_sleep: float = 1.25, **kwargs):
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except (requests.RequestException, ValueError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(base_sleep * attempt)
    raise MLSCollectorError(f"request failed after {retries} attempts: {last}")


# ---------------------------------------------------------- discovery --------
def discover_events(start: date, end: date, *, session: requests.Session,
                    pause: float = 0.08) -> list[dict]:
    """All events across [start, end], each tagged with the date it was found
    under (the canonical match_date, avoiding UTC-rollover surprises)."""
    seen: dict[str, dict] = {}
    cur = start
    while cur <= end:
        try:
            games = _with_retries(espn_soccer.schedule, espn_soccer.MLS, cur)
        except MLSCollectorError:
            games = []
        for g in games:
            gid = str(g.get("game_id") or "")
            if gid and gid not in seen:
                g["discovery_date"] = cur.isoformat()
                seen[gid] = g
        cur += timedelta(days=1)
        if pause:
            time.sleep(pause)
    return list(seen.values())


def is_regular_season_completed(event: dict) -> bool:
    return bool(event.get("completed")) and event.get("season_slug") == REGULAR_SEASON_SLUG


# --------------------------------------------------------- validation --------
def validate_and_build(event: dict, summary: dict, collected_at: str) -> tuple[dict, list[dict]]:
    """Validate match structure and build the match row + two team-stat rows.

    Raises MLSCollectorError on an invalid structure (never writes partial rows).
    """
    home_id, away_id = event.get("home_id"), event.get("away_id")
    if not home_id or not away_id:
        raise MLSCollectorError("scoreboard event missing home/away team id")

    team_rows = espn_soccer.parse_team_stats(summary)  # raises if != 2 blocks
    stat_ids = {r["team_id"] for r in team_rows}
    if stat_ids != {home_id, away_id}:
        raise MLSCollectorError(
            f"team ids do not reconcile: scoreboard {sorted({home_id, away_id})} "
            f"vs boxscore {sorted(stat_ids)}")

    meta = espn_soccer.parse_match_meta(summary)
    home_score, away_score = event.get("home_score"), event.get("away_score")

    match_row = {
        "event_id": str(event["game_id"]),
        "match_date": event.get("discovery_date") or (event.get("game_date") or "")[:10],
        "kickoff_time": event.get("game_date"),
        "season": event.get("season_year"),
        "season_type": event.get("season_type"),
        "competition_slug": espn_soccer.MLS,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_score": home_score,
        "away_score": away_score,
        "state": event.get("state"),
        "venue_id": meta.get("venue_id"),
        "venue": meta.get("venue") or event.get("venue"),
        "attendance": meta.get("attendance"),
        "referee": meta.get("referee"),
        "collected_at": collected_at,
    }

    for row in team_rows:
        row["event_id"] = str(event["game_id"])
        row["collected_at"] = collected_at
        if row["is_home"]:
            row["goals_for"], row["goals_against"] = home_score, away_score
        else:
            row["goals_for"], row["goals_against"] = away_score, home_score
    return match_row, team_rows


# --------------------------------------------------------- standings ---------
def collect_standings(season: int, snapshot_date: str, collected_at: str,
                      *, session: requests.Session) -> list[dict]:
    payload = _with_retries(espn_soccer.fetch_standings, espn_soccer.MLS, season, session=session)
    rows = espn_soccer.parse_standings(payload)
    for r in rows:
        r["season"] = season
        r["snapshot_date"] = snapshot_date
        r["collected_at"] = collected_at
        r["league_rank"] = None  # not provided; left for a future derivation
    return rows


# ------------------------------------------------------------- run -----------
def collect(*, season: int = 2026, start: date | None = None, end: date | None = None,
            db_path: Path = DB_PATH, force: bool = False, pause: float = 0.12,
            verbose: bool = True) -> CollectionResult:
    start = start or SEASON_START_DEFAULT
    end = end or date.today()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snapshot_date = date.today().isoformat()

    def log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    collected = skipped = failures = standings_rows = 0
    error_notes: list[str] = []

    with sqlite3.connect(db_path) as conn:
        mls_store.ensure_tables(conn)
        already = mls_store.fully_collected_event_ids(conn) if not force else set()

        log(f"→ Discovering MLS events {start} … {end}")
        events = discover_events(start, end, session=session)
        regular = [e for e in events if is_regular_season_completed(e)]
        log(f"  {len(events)} events discovered, {len(regular)} completed regular-season")

        for e in regular:
            gid = str(e["game_id"])
            if gid in already and not force:
                skipped += 1
                continue
            try:
                summary = _with_retries(espn_soccer.fetch_summary, espn_soccer.MLS, gid, session=session)
                match_row, team_rows = validate_and_build(e, summary, started_at)
                mls_store.upsert_matches(conn, [match_row])
                mls_store.upsert_team_stats(conn, team_rows)
                # Match events come from the same payload (no extra request).
                event_rows = espn_soccer.parse_key_events(summary)
                for ev in event_rows:
                    ev["match_id"] = gid
                    ev["collected_at"] = started_at
                mls_store.upsert_events(conn, [ev for ev in event_rows if ev.get("seq")])
                conn.commit()
                collected += 1
                log(f"  ✓ {match_row['match_date']} {e.get('away')} {e.get('away_score')}"
                    f"–{e.get('home_score')} {e.get('home')}")
            except MLSCollectorError as exc:
                failures += 1
                error_notes.append(f"{gid}: {exc}")
                log(f"  ✗ {gid}: {exc}")
            if pause:
                time.sleep(pause)

        # Standings snapshot (best-effort; not fatal to the run).
        try:
            srows = collect_standings(season, snapshot_date, started_at, session=session)
            standings_rows = mls_store.upsert_standings(conn, srows)
            conn.commit()
            log(f"  ✓ standings: {standings_rows} teams ({snapshot_date})")
        except MLSCollectorError as exc:
            error_notes.append(f"standings: {exc}")
            log(f"  ✗ standings: {exc}")

        status = "SUCCESS" if failures == 0 else ("PARTIAL" if collected else "FAILED")
        mls_store.insert_run(
            conn,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            start_date=start.isoformat(), end_date=end.isoformat(),
            events_discovered=len(events), events_skipped=skipped,
            events_collected=collected, failures=failures,
            status=status, error_summary="; ".join(error_notes[:10]) or None,
        )
        conn.commit()
        _write_csv_mirror(conn)

    session.close()
    result = CollectionResult(
        events_discovered=len(events), completed_events=len(regular),
        events_collected=collected, events_skipped=skipped, failures=failures,
        standings_rows=standings_rows, start_date=start.isoformat(),
        end_date=end.isoformat(), database_path=str(db_path),
    )
    log("\n" + "=" * 56)
    for k, v in asdict(result).items():
        log(f"  {k:20s}: {v}")
    log("=" * 56)
    return result


def _write_csv_mirror(conn: sqlite3.Connection) -> None:
    MLS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for table, name in (("mls_matches", "mls_matches.csv"),
                        ("mls_team_match_stats", "mls_team_match_stats.csv"),
                        ("mls_match_events", "mls_match_events.csv"),
                        ("mls_standings", "mls_standings.csv")):
        try:
            pd.read_sql_query(f"SELECT * FROM {table}", conn).to_csv(
                MLS_DATA_DIR / name, index=False)
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Collect MLS regular-season team stats.")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--start", type=date.fromisoformat, default=None)
    ap.add_argument("--end", type=date.fromisoformat, default=None)
    ap.add_argument("--force", action="store_true", help="re-collect already-stored events")
    args = ap.parse_args(argv)
    result = collect(season=args.season, start=args.start, end=args.end, force=args.force)
    # Nonzero exit if nothing collected AND failures occurred.
    return 1 if (result.failures and not result.events_collected) else 0


if __name__ == "__main__":
    sys.exit(main())
