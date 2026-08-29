"""Fetch NCAAF season context from ESPN into SQLite: prior-season records, that
season's leading passer per team, and this season's rosters and head coaches.

Deliberately **not** a daily job. Everything here is season-stable — a completed
season's record never changes, and rosters move on a scale of weeks — so the daily run
refreshes it at most weekly and reads SQLite the rest of the time. The alternative,
~530 requests every morning, would add minutes to a run whose answer had not changed.

Two provider quirks discovered by testing rather than by reading docs, both load-bearing:

- **The standings endpoint is genuinely historical** and division-scoped. Group 80 is
  FBS (136 teams for 2025), group 81 FCS (129). A team on the slate with no FBS row is
  an FCS opponent, which is how the mismatch notice is derived — no separate lookup.
- **The leaders endpoint is genuinely historical too**: USC returns Caleb Williams for
  2023, Miller Moss for 2024, Jayden Maiava for 2025. This is what makes "last season's
  leading passer" trustworthy.

The coach endpoints are *not* historical — every season echoes the current coach — so
nothing here tries to read a past coach. It records the present one instead; see
``src/ncaaf_store``.
"""

from __future__ import annotations

import json
import re
import sqlite3
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from src import ncaaf_store
from src.config import DB_PATH

CORE = "http://sports.core.api.espn.com/v2/sports/football/leagues/college-football"
SITE = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"
# Standings sit on a *different* base than the rest of the site API — `apis/v2`, not
# `apis/site/v2`. Using the latter returns a 404 body that parses as an empty payload,
# so the collector silently wrote zero rows rather than failing.
STANDINGS = "https://site.api.espn.com/apis/v2/sports/football/college-football"

# ESPN group ids. The division a team plays in is the single most useful fact about an
# early-season college game, and this is where it comes from.
DIVISIONS = {80: "FBS", 81: "FCS"}

_ID_RE = re.compile(r"/(?:athletes|coaches)/(\d+)")
_TEAM_RE = re.compile(r"/teams/(\d+)")
# Short on purpose, and the opposite of what the publish check needs. ESPN's standings
# host returns 403 for a full Chrome UA string while accepting a bare "Mozilla/5.0";
# Cloudflare, in scripts/publish_pages, does the reverse. Both were established by
# trying them, and neither is guessable — do not "tidy" this into a shared constant.
_USER_AGENT = "Mozilla/5.0"


def _context() -> ssl.SSLContext | None:
    """Python on macOS ships without a CA bundle, so a plain urlopen fails against
    every https host. Same fix the publish check uses."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return None


def fetch_json(url: str, timeout: float = 25.0) -> dict | None:
    """None on any failure. Season context is enrichment: a page without it says less,
    but a collector failure must never take down the daily run."""
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout,
                                    context=_context()) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def _athlete_id(ref: str | None) -> str | None:
    """ESPN's `$ref` URLs carry the id, so the id costs no extra request. Resolving the
    ref would be one more round trip per team purely to learn something already in the
    string."""
    found = _ID_RE.search(str(ref or ""))
    return found.group(1) if found else None


def season_records(season: int) -> list[tuple]:
    """Every team's final record for a completed season, both divisions."""
    now = datetime.now().isoformat(timespec="seconds")
    rows: list[tuple] = []
    for group, division in DIVISIONS.items():
        payload = fetch_json(
            f"{STANDINGS}/standings?season={season}&group={group}")
        if not payload:
            continue

        def walk(node: dict, conference: str | None) -> None:
            name = node.get("name") or conference
            for entry in (node.get("standings") or {}).get("entries") or []:
                team = entry.get("team") or {}
                stats = {s.get("name"): s for s in entry.get("stats") or []}
                overall = (stats.get("overall") or {}).get("displayValue")
                wins = _int((stats.get("wins") or {}).get("value"))
                losses = _int((stats.get("losses") or {}).get("value"))
                if wins is None or losses is None:
                    wins, losses = _split_record(overall)
                rows.append((season, str(team.get("id")), team.get("displayName"),
                             division, name, overall, wins, losses, now))
            for child in node.get("children") or []:
                walk(child, name)

        walk(payload, None)
    return rows


def _int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _split_record(overall: str | None) -> tuple[int | None, int | None]:
    match = re.match(r"^\s*(\d+)\s*-\s*(\d+)", str(overall or ""))
    return (int(match.group(1)), int(match.group(2))) if match else (None, None)


def team_leading_passer(season: int, team_id: str) -> tuple[str, float | None] | None:
    """(athlete_id, passing yards) for that season's passing leader."""
    payload = fetch_json(f"{CORE}/seasons/{season}/types/2/teams/{team_id}/leaders")
    if not payload:
        return None
    categories = {c.get("name"): c for c in payload.get("categories") or []}
    leaders = (categories.get("passingYards") or {}).get("leaders") or []
    if not leaders:
        return None
    athlete_id = _athlete_id((leaders[0].get("athlete") or {}).get("$ref"))
    return (athlete_id, _float(leaders[0].get("value"))) if athlete_id else None


def _float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def athlete_now(season: int, athlete_id: str) -> dict | None:
    """Where this player is in ``season`` — name, position, whether he is still active,
    and the team he is on. One request, and it cannot truncate the way a roster can."""
    payload = fetch_json(f"{CORE}/seasons/{season}/athletes/{athlete_id}")
    if not payload:
        return None
    team = _TEAM_RE.search(str((payload.get("team") or {}).get("$ref") or ""))
    return {
        "name": payload.get("displayName"),
        "position": (payload.get("position") or {}).get("abbreviation"),
        "active": bool(payload.get("active")),
        "team_id": team.group(1) if team else None,
    }


def passer_row(prior_season: int, current_season: int, team_id: str) -> tuple | None:
    """The stored row for a team's prior-season leading passer, including where he is
    now. ``status`` is None when the follow-up lookup failed — the page must be able to
    tell "we checked and he left" apart from "we could not check"."""
    leader = team_leading_passer(prior_season, team_id)
    if not leader:
        return None
    athlete_id, yards = leader
    now = athlete_now(current_season, athlete_id)
    status = current_team = name = position = None
    if now is not None:
        name, position = now["name"], now["position"]
        if not now["active"]:
            status = "inactive"
        elif now["team_id"] and now["team_id"] != str(team_id):
            status, current_team = "transferred", now["team_id"]
        else:
            status = "returning"
    return (prior_season, str(team_id), athlete_id, name, position, yards,
            status, current_team, datetime.now().isoformat(timespec="seconds"))


def team_coach(season: int, team_id: str) -> tuple | None:
    """Today's head coach, recorded for a comparison only a future season can make.
    See ``src/ncaaf_store``."""
    payload = fetch_json(f"{SITE}/teams/{team_id}/roster?season={season}")
    coaches = (payload or {}).get("coach") or []
    if not coaches:
        return None
    coach = coaches[0]
    name = f"{coach.get('firstName', '')} {coach.get('lastName', '')}".strip()
    return (season, str(team_id), str(coach.get("id")), name or None,
            datetime.now().isoformat(timespec="seconds"))


def _fresh_team_ids(conn: sqlite3.Connection, season: int, max_age_days: int) -> set[str]:
    """Teams whose passer row was checked recently enough to leave alone. Without this
    the collector would re-ask ESPN the same ~530 questions every morning; the answers
    change on a scale of weeks."""
    if max_age_days <= 0:
        return set()
    cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT team_id FROM ncaaf_team_passers WHERE season = ? AND collected_at > ?",
        (season, cutoff)).fetchall()
    return {str(r[0]) for r in rows}


def collect(*, prior_season: int, current_season: int,
            db_path: Path = DB_PATH, pause: float = 0.05,
            team_ids: list[str] | None = None, max_age_days: int = 7,
            verbose: bool = False) -> dict:
    """Collect prior-season records, that season's leading passer and where he is now,
    and the current head coach.

    Season-stable by nature, so teams checked within ``max_age_days`` are skipped and a
    daily caller does almost no work after the first run. ``team_ids`` narrows the
    per-team pass; by default every team with a prior-season record is covered, so any
    game's page can be rendered without a fetch.
    """
    summary = {"team_seasons": 0, "passers": 0, "coaches": 0,
               "teams": 0, "skipped": 0, "errors": 0}
    records = season_records(prior_season)
    with sqlite3.connect(db_path) as conn:
        ncaaf_store.ensure_tables(conn)
        summary["team_seasons"] = ncaaf_store.upsert_team_seasons(conn, records)

        targets = [str(t) for t in (team_ids if team_ids is not None
                                    else [r[1] for r in records])]
        fresh = _fresh_team_ids(conn, prior_season, max_age_days)
        for team_id in targets:
            if team_id in fresh:
                summary["skipped"] += 1
                continue
            summary["teams"] += 1
            try:
                row = passer_row(prior_season, current_season, team_id)
                if row:
                    summary["passers"] += ncaaf_store.upsert_passers(conn, [row])
                coach = team_coach(current_season, team_id)
                if coach:
                    summary["coaches"] += ncaaf_store.upsert_coaches(conn, [coach])
            except Exception:                                    # noqa: BLE001
                summary["errors"] += 1
            # Commit as we go. A full pass is ~530 requests over ten minutes or more;
            # committing once at the end would throw all of it away on a Ctrl-C or a
            # dropped connection, and the next run would start from nothing.
            if summary["teams"] % 20 == 0:
                conn.commit()
            if pause:
                time.sleep(pause)
            if verbose:
                print(f"  {team_id}: {summary['passers']} passers")
        conn.commit()
    return summary
