"""Fetch current-season standings from ESPN for the leagues that have divisions.

One request per league, walking ESPN's group tree (league -> conference -> division)
because the entries only exist at the deepest level — asking for the top level returns
groups with zero entries, which reads as "no data" rather than "look further down".

Non-fatal by construction: a league that fails returns nothing and the others still
write. Standings are context, and context must never fail a data run.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from src.config import DB_PATH
from src.ncaaf_collector import fetch_json
from src.standings_store import ensure_tables, upsert

STANDINGS = "https://site.api.espn.com/apis/v2/sports"


@dataclass(frozen=True)
class LeagueSpec:
    path: str                       # ESPN sport/league path
    ties_stat: str | None = None    # the sport's third outcome, where it has one


# MLS is absent on purpose: it already has mls_standings, in soccer's own shape
# (points, draws, goal difference). NCAAF is absent because it has no stable divisions
# to rank within — the same reason prior_season excludes it.
LEAGUES: dict[str, LeagueSpec] = {
    "WNBA": LeagueSpec("basketball/wnba"),
    "NFL": LeagueSpec("football/nfl", ties_stat="ties"),
    "NBA": LeagueSpec("basketball/nba"),
    "NHL": LeagueSpec("hockey/nhl", ties_stat="otLosses"),
}


def _stat(entry: dict, name: str):
    for stat in entry.get("stats") or []:
        if stat.get("name") == name:
            return stat
    return None


def _num(entry: dict, name: str) -> float | None:
    stat = _stat(entry, name)
    if stat is None:
        return None
    try:
        return float(stat.get("value"))
    except (TypeError, ValueError):
        return None


def _text(entry: dict, name: str) -> str | None:
    stat = _stat(entry, name)
    if stat is None:
        return None
    value = stat.get("displayValue") or stat.get("summary")
    return str(value) if value not in (None, "") else None


def _walk(node: dict, conference: str | None, division: str | None, out: list) -> None:
    """Collect (conference, division, entries) from every level that actually has any."""
    name = node.get("name")
    entries = (node.get("standings") or {}).get("entries") or []
    if entries:
        out.append((conference, division or name, entries))
    for child in node.get("children") or []:
        # The first level under the league is the conference; the next is the division.
        if conference is None:
            _walk(child, name, None, out)
        else:
            _walk(child, conference, child.get("name"), out)


def league_rows(league: str, season: int, snapshot: str) -> list[dict]:
    spec = LEAGUES.get(league)
    if spec is None:
        return []
    # seasontype=2 is the regular season. Without it ESPN serves *preseason* records,
    # and on 1 September the NFL page showed 3-0 and 1-1-1 as if they were standings —
    # exhibition results wearing a standings table. The MLB path already asks StatsAPI
    # for regularSeason explicitly, for the same reason.
    payload = fetch_json(
        f"{STANDINGS}/{spec.path}/standings?season={season}&level=3&seasontype=2")
    if not payload:
        return []
    groups: list = []
    _walk(payload, None, None, groups)
    collected = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows: list[dict] = []
    for conference, division, entries in groups:
        # ESPN returns a group already ordered; rank is that order, not a stat, because
        # `playoffSeed` is league-wide and would make every division start at a
        # different number.
        for rank, entry in enumerate(entries, 1):
            team = entry.get("team") or {}
            team_id = str(team.get("id") or "")
            if not team_id:
                continue
            rows.append({
                "league": league, "season": season, "snapshot_date": snapshot,
                "team_id": team_id,
                "team_name": team.get("displayName"),
                "team_abbr": team.get("abbreviation"),
                "conference": conference, "division": division,
                "division_rank": rank,
                "wins": int(_num(entry, "wins") or 0),
                "losses": int(_num(entry, "losses") or 0),
                "ties": int(_num(entry, spec.ties_stat) or 0) if spec.ties_stat else 0,
                "win_pct": _num(entry, "winPercent"),
                "games_behind": _num(entry, "gamesBehind"),
                "playoff_seed": (int(_num(entry, "playoffSeed"))
                                 if _num(entry, "playoffSeed") is not None else None),
                "streak": _text(entry, "streak"),
                "last_ten": _text(entry, "Last Ten Games"),
                "home_record": _text(entry, "Home"),
                "road_record": _text(entry, "Road"),
                "logo": next((l.get("href") for l in (team.get("logos") or [])
                              if l.get("href")), None),
                "collected_at": collected,
            })
    return rows


def collect(leagues: list[str] | None = None, on: date | None = None,
            db_path: Path = DB_PATH) -> dict[str, int]:
    """Fetch and store today's standings. Returns {league: rows written}."""
    slate = on or date.today()
    snapshot = slate.isoformat()
    written: dict[str, int] = {}
    with sqlite3.connect(db_path) as conn:
        ensure_tables(conn)
        for league in (leagues or ["MLB", *LEAGUES]):
            try:
                rows = (mlb_rows(slate.year, snapshot) if league == "MLB"
                        else league_rows(league, slate.year, snapshot))
            except Exception:
                continue            # context must never fail a data run
            if rows:
                written[league] = upsert(conn, rows)
        conn.commit()
    return written


# --- MLB: StatsAPI, not ESPN ---------------------------------------------------------
# The MLB slate comes from StatsAPI, so its team ids are StatsAPI ids. ESPN's standings
# carry ESPN ids, and the two do not match — joining them would mean joining on team
# *names*, which this project refuses (see the coding standards). Taking MLB standings
# from the same source as the MLB schedule keeps the join on ids. The other leagues are
# scheduled from ESPN, so ESPN standings match them natively.
_MLB_STANDINGS = "https://statsapi.mlb.com/api/v1/standings"
_MLB_DIVISIONS = "https://statsapi.mlb.com/api/v1/divisions?sportId=1"


def _mlb_divisions() -> dict[int, tuple[str, str]]:
    """division id -> (division name, league/conference name)."""
    import requests

    payload = requests.get(_MLB_DIVISIONS, timeout=20).json()
    out: dict[int, tuple[str, str]] = {}
    for div in payload.get("divisions") or []:
        did = div.get("id")
        name = div.get("name") or ""
        # "American League East" -> conference "American League"
        conference = name.rsplit(" ", 1)[0] if name else None
        if did:
            out[int(did)] = (name, conference or "")
    return out


def mlb_rows(season: int, snapshot: str) -> list[dict]:
    import requests

    divisions = _mlb_divisions()
    payload = requests.get(
        f"{_MLB_STANDINGS}?leagueId=103,104&season={season}"
        f"&standingsTypes=regularSeason", timeout=20).json()
    collected = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows: list[dict] = []
    for record in payload.get("records") or []:
        did = (record.get("division") or {}).get("id")
        division, conference = divisions.get(int(did), (None, None)) if did else (None, None)
        for team in record.get("teamRecords") or []:
            info = team.get("team") or {}
            team_id = str(info.get("id") or "")
            if not team_id:
                continue
            # StatsAPI writes the division leader's games back as "-", not 0.
            gb_raw = team.get("gamesBack")
            try:
                games_behind = 0.0 if gb_raw in ("-", None, "") else float(gb_raw)
            except (TypeError, ValueError):
                games_behind = None
            try:
                pct = float(team.get("winningPercentage"))
            except (TypeError, ValueError):
                pct = None
            splits = {r.get("type"): r for r in
                      ((team.get("records") or {}).get("splitRecords") or [])}

            def _split(kind):
                r = splits.get(kind)
                return f"{r['wins']}-{r['losses']}" if r else None

            rows.append({
                "league": "MLB", "season": season, "snapshot_date": snapshot,
                "team_id": team_id,
                # StatsAPI's standings "name" is the nickname ("Rays"); the schedule's
                # full name lives elsewhere, and the page already has it from the game.
                "team_name": info.get("name"),
                "team_abbr": None,
                "conference": conference, "division": division,
                "division_rank": int(team.get("divisionRank") or 0) or None,
                "wins": int(team.get("wins") or 0),
                "losses": int(team.get("losses") or 0),
                "ties": 0,
                "win_pct": pct,
                "games_behind": games_behind,
                "playoff_seed": None,
                "streak": (team.get("streak") or {}).get("streakCode"),
                "last_ten": _split("lastTen"),
                "home_record": _split("home"),
                "road_record": _split("away"),
                # StatsAPI has no logo field; the CDN path is derived from the team id,
                # which is the same convention src/mlb_api already uses for the slate.
                "logo": f"https://www.mlbstatic.com/team-logos/{team_id}.svg",
                "collected_at": collected,
            })
    return rows


if __name__ == "__main__":
    for name, count in collect().items():
        print(f"{name}: {count} teams")


# --- MLS: names only ------------------------------------------------------------------
_MLS_STANDINGS = f"{STANDINGS}/soccer/usa.1/standings"


def mls_team_lookup(season: int) -> list[dict]:
    """``mls_standings`` is keyed by team id and holds no names, because the MLS
    schedule feed carries none either. ESPN's table uses the *same* ids, so it can
    supply the missing names and crests without the standings themselves moving source.
    """
    payload = fetch_json(f"{_MLS_STANDINGS}?season={season}&level=3")
    if not payload:
        return []
    groups: list = []
    _walk(payload, None, None, groups)
    rows = []
    for _conf, _div, entries in groups:
        for entry in entries:
            team = entry.get("team") or {}
            tid = str(team.get("id") or "")
            if not tid:
                continue
            rows.append({
                "team_id": tid,
                "name": team.get("displayName"),
                "abbr": team.get("abbreviation"),
                "logo": next((l.get("href") for l in (team.get("logos") or [])
                              if l.get("href")), None),
            })
    return rows


def collect_mls_teams(season: int, db_path: Path = DB_PATH) -> int:
    rows = mls_team_lookup(season)
    if not rows:
        return 0
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mls_teams (
                team_id TEXT PRIMARY KEY, name TEXT, abbr TEXT, logo TEXT)
        """)
        conn.executemany(
            "INSERT OR REPLACE INTO mls_teams (team_id, name, abbr, logo) "
            "VALUES (?, ?, ?, ?)",
            [(r["team_id"], r["name"], r["abbr"], r["logo"]) for r in rows])
        conn.commit()
    return len(rows)
