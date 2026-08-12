"""Shared ESPN box-score collector — player game logs for any sport ESPN covers.

`src/wnba_collector.py` proved the pattern: ESPN's `summary` endpoint returns a full player
box score per game, keyed by athlete id. That collector hard-codes basketball, so NHL, NBA
and CBB each needed a copy of 670 lines to differ in a stat map and two table names.

This is the engine. A sport is a **`SportSpec`** — its ESPN path, table prefix, stat
vocabulary and column list — and everything else (request/retry, schedule paging, stat
parsing, incremental skip, upsert) is shared.

**Verified before it was written** (2026-08-12): box scores resolve back to at least 2011
for NHL, 2010 for NBA and 2015 for CBB, with athlete ids on every row. So this backfills
history, it is not a live-only feed — which matters because [Method §2](../docs/engineering/METHOD.md)
needs multiple seasons to split-half anything.

**Why not fold WNBA into this immediately.** WNBA is live and graded daily; its table has
a settled schema and a scorer reading it. Rewriting it to prove a refactor would risk the
one basketball surface that works, for no user-visible gain. The engine is written so WNBA
*can* move later — its spec is included and tested against the same parser — but the
migration is a separate, deliberate step.

**Cross-checking is the point of starting with NBA.** We hold six ingested vendor seasons
of NBA, so a collector's output can be compared against a second independent source.
That is exactly the check that caught ESPN silently returning 19 of 169 CBB games.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

from src.config import DB_PATH

_BASE = "https://site.api.espn.com/apis/site/v2/sports/{path}/{endpoint}"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 SportsToday/1.0"),
    "Accept": "application/json,text/plain,*/*",
}

# Stats that arrive as "made-attempted" ("8-15") and expand into two columns.
_SPLIT_SUFFIXES = ("_made", "_attempted")


class CollectorError(RuntimeError):
    """The source could not be collected or parsed safely."""


@dataclass(frozen=True)
class SportSpec:
    """Everything that differs between sports.

    ``stat_aliases`` maps ESPN's column labels (lower-cased, punctuation stripped) onto
    canonical names; ``columns`` lists the canonical names to store. A name in ``splits``
    is stored as ``<name>_made`` / ``<name>_attempted``; a name in ``clock`` is parsed from
    ``MM:SS`` into float minutes.

    ``groups`` and ``limit`` exist because ESPN truncates college scoreboards — see
    `src/espn_scoreboard.fetch`. Getting them wrong shows a partial slate silently.
    """
    key: str
    label: str
    espn_path: str
    table_prefix: str
    stat_aliases: dict[str, str]
    columns: tuple[str, ...]
    splits: tuple[str, ...] = ()
    clock: tuple[str, ...] = ()
    groups: tuple[int, ...] = ()
    limit: int = 100
    # Autumn-to-spring sports label a season by the year it began; the ESPN payload
    # already carries `season.year`, so this is only used for default date windows.
    spanning: bool = False


_BASKETBALL_ALIASES = {
    "min": "minutes", "minutes": "minutes",
    "fg": "field_goals", "fieldgoals": "field_goals",
    "3pt": "three_pointers", "3p": "three_pointers",
    "threepointfieldgoals": "three_pointers",
    "ft": "free_throws", "freethrows": "free_throws",
    "oreb": "offensive_rebounds", "offensiverebounds": "offensive_rebounds",
    "dreb": "defensive_rebounds", "defensiverebounds": "defensive_rebounds",
    "reb": "rebounds", "totalrebounds": "rebounds",
    "ast": "assists", "assists": "assists",
    "stl": "steals", "steals": "steals",
    "blk": "blocks", "blocks": "blocks",
    "to": "turnovers", "turnovers": "turnovers",
    "pf": "personal_fouls", "fouls": "personal_fouls",
    "+/-": "plus_minus", "plusminus": "plus_minus",
    "pts": "points", "points": "points",
}

_BASKETBALL_COLUMNS = ("minutes", "field_goals", "three_pointers", "free_throws",
                       "offensive_rebounds", "defensive_rebounds", "rebounds", "assists",
                       "steals", "blocks", "turnovers", "personal_fouls", "plus_minus",
                       "points")
_BASKETBALL_SPLITS = ("field_goals", "three_pointers", "free_throws")

# NHL ships skaters and goalies as *different stat sets* in separate groups. One wide table
# with nulls keeps "one row per player-game" — the shape every scorer in this app expects —
# and `player_group` says which kind of row it is. Two tables would mean every downstream
# query knowing about both.
_HOCKEY_ALIASES = {
    "toi": "time_on_ice", "pptoi": "pp_time_on_ice", "shtoi": "sh_time_on_ice",
    "estoi": "es_time_on_ice", "shft": "shifts",
    # **`S` is shots on goal; `SOG` is a dead column that is always 0.** Mapping them the
    # obvious way round produced a `shots_on_goal` of zero for all 1,548 skaters in a
    # five-day sample while the real data sat in a field called `shots`. Caught because a
    # team SOG of 0.0 per game is impossible — the true figure here is 26.7, and NHL
    # averages ~30. `SOG` is deliberately mapped to a name no spec stores.
    "g": "goals", "a": "assists",
    "s": "shots_on_goal", "sog": "_espn_sog_unused",
    "sm": "shots_missed", "bs": "blocked_shots", "ht": "hits", "tk": "takeaways",
    "gv": "giveaways", "fw": "faceoffs_won", "fl": "faceoffs_lost", "fo%": "faceoff_pct",
    "pn": "penalties", "pim": "penalty_minutes", "+/-": "plus_minus",
    "ga": "goals_against", "sa": "shots_against", "sv": "saves", "sv%": "save_pct",
    "essv": "es_saves", "ppsv": "pp_saves", "shsv": "sh_saves",
    "sos": "shootout_saves", "sosa": "shootout_shots_against",
}

_HOCKEY_COLUMNS = ("time_on_ice", "pp_time_on_ice", "sh_time_on_ice", "es_time_on_ice",
                   "shifts", "goals", "assists", "shots_on_goal", "shots_missed",
                   "blocked_shots", "hits", "takeaways", "giveaways", "faceoffs_won",
                   "faceoffs_lost", "faceoff_pct", "penalties", "penalty_minutes",
                   "plus_minus", "goals_against", "shots_against", "saves", "save_pct",
                   "es_saves", "pp_saves", "sh_saves")

SPORTS: dict[str, SportSpec] = {
    "nba": SportSpec("nba", "NBA", "basketball/nba", "nba_espn",
                     _BASKETBALL_ALIASES, _BASKETBALL_COLUMNS, _BASKETBALL_SPLITS,
                     clock=("minutes",), spanning=True),
    "cbb": SportSpec("cbb", "CBB", "basketball/mens-college-basketball", "cbb_espn",
                     _BASKETBALL_ALIASES, _BASKETBALL_COLUMNS, _BASKETBALL_SPLITS,
                     clock=("minutes",), groups=(50,), limit=300, spanning=True),
    "nhl": SportSpec("nhl", "NHL", "hockey/nhl", "nhl_espn",
                     _HOCKEY_ALIASES, _HOCKEY_COLUMNS,
                     clock=("time_on_ice", "pp_time_on_ice", "sh_time_on_ice",
                            "es_time_on_ice"), spanning=True),
    # Included so the shared parser is exercised against the schema we already trust.
    # The live WNBA tables are still written by src/wnba_collector.py — see the module
    # docstring on why that migration is deliberate and separate.
    "wnba": SportSpec("wnba", "WNBA", "basketball/wnba", "wnba_espn",
                      _BASKETBALL_ALIASES, _BASKETBALL_COLUMNS, _BASKETBALL_SPLITS,
                      clock=("minutes",)),
}

_IDENTITY = ("game_id", "game_date", "season", "season_type", "player_id", "player_name",
             "position", "jersey", "team_id", "team", "team_abbr", "opponent_id",
             "opponent", "opponent_abbr", "home_away", "player_group", "started", "active")


@dataclass
class CollectionResult:
    sport: str
    games_seen: int = 0
    completed_games: int = 0
    games_downloaded: int = 0
    player_rows: int = 0
    skipped_existing: int = 0
    failures: list[str] = field(default_factory=list)


# --- parsing helpers (pure; no network) ---------------------------------------------

def clean_label(value: object) -> str:
    raw = str(value or "").strip().lower()
    compact = "".join(ch for ch in raw if ch.isalnum() or ch in {"+", "-", "/", "%"})
    return compact


def number(value: object) -> float | None:
    if value in (None, "", "--", "DNP", "N/A", "-"):
        return None
    text = str(value).replace(",", "").strip()
    if text.startswith("."):          # ESPN writes save/faceoff rates as ".714"
        text = "0" + text
    try:
        return float(text)
    except ValueError:
        return None


def made_attempted(value: object) -> tuple[float | None, float | None]:
    if value in (None, "", "--"):
        return None, None
    text = str(value).strip()
    for sep in ("-", "/"):
        if sep in text:
            left, right = text.split(sep, 1)
            return number(left), number(right)
    return number(value), None


def clock_minutes(value: object) -> float | None:
    """``MM:SS`` (or ``HH:MM:SS``) into float minutes; a bare number passes through."""
    if value in (None, "", "--", "DNP"):
        return None
    text = str(value).strip()
    if ":" in text:
        parts = text.split(":")
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            return None
        if len(nums) == 2:
            return nums[0] + nums[1] / 60.0
        if len(nums) == 3:
            return nums[0] * 60 + nums[1] + nums[2] / 60.0
        return None
    return number(value)


def parse_event(event: dict[str, Any]) -> dict[str, Any]:
    """One scheduled game, flattened. Identical across sports — ESPN's scoreboard shape
    does not vary by league."""
    comp = (event.get("competitions") or [{}])[0]
    # ESPN dates are UTC instants; a 7pm ET tip on 9 Jan is "2026-01-10T00:00Z". Storing
    # that as `game_date` makes every `WHERE game_date = '...'` silently wrong — it cost a
    # validation run that reported 24% agreement against our vendor feed until the shift
    # was spotted, then 99.1%. So keep both: `start_time` is the instant, `game_date` is
    # the league's own calendar day (US/Eastern for the sports here).
    start_raw = event.get("date")
    local_day = None
    if start_raw:
        ts = pd.to_datetime(start_raw, errors="coerce", utc=True)
        if pd.notna(ts):
            local_day = str(ts.tz_convert("America/New_York").date())
    sides = comp.get("competitors") or []
    home = next((c for c in sides if c.get("homeAway") == "home"), {})
    away = next((c for c in sides if c.get("homeAway") == "away"), {})
    status = (event.get("status") or {}).get("type") or {}
    return {
        "game_id": str(event.get("id") or ""),
        "game_date": local_day,
        "start_time": start_raw,
        "season": (event.get("season") or {}).get("year"),
        "season_type": (event.get("season") or {}).get("type"),
        "status_name": status.get("name"),
        "is_completed": bool(status.get("completed")),
        "home_team_id": str((home.get("team") or {}).get("id") or ""),
        "home_team": (home.get("team") or {}).get("displayName"),
        "home_score": pd.to_numeric(home.get("score"), errors="coerce"),
        "away_team_id": str((away.get("team") or {}).get("id") or ""),
        "away_team": (away.get("team") or {}).get("displayName"),
        "away_score": pd.to_numeric(away.get("score"), errors="coerce"),
        "venue": (comp.get("venue") or {}).get("fullName"),
    }


def parse_player_rows(payload: dict[str, Any], game: dict[str, Any],
                      spec: SportSpec) -> list[dict[str, Any]]:
    """Every athlete row in a game's box score, in this sport's schema.

    Returns ``[]`` when the payload carries no player section — an ordinary answer for a
    postponed game or one ESPN has not finished processing, and **not** an error. Silently
    writing zero rows for a completed game would be, which is why the caller counts them.
    """
    out: list[dict[str, Any]] = []
    for section in payload.get("boxscore", {}).get("players") or []:
        team = section.get("team") or {}
        team_id = str(team.get("id") or "")
        if team_id == game["home_team_id"]:
            home_away, opp_id, opp = "home", game["away_team_id"], game["away_team"]
        elif team_id == game["away_team_id"]:
            home_away, opp_id, opp = "away", game["home_team_id"], game["home_team"]
        else:
            home_away, opp_id, opp = "", "", None
        for group in section.get("statistics") or []:
            labels = [clean_label(x) for x in (group.get("names")
                                               or group.get("labels") or [])]
            canonical = [spec.stat_aliases.get(x, x) for x in labels]
            for entry in group.get("athletes") or []:
                athlete = entry.get("athlete") or {}
                pid = str(athlete.get("id") or "")
                if not pid:
                    continue          # never join on names
                stats = dict(zip(canonical, entry.get("stats") or []))
                row: dict[str, Any] = {
                    "game_id": game["game_id"], "game_date": game["game_date"],
                    "season": game["season"], "season_type": game["season_type"],
                    "player_id": pid,
                    "player_name": athlete.get("displayName") or athlete.get("fullName"),
                    "position": (athlete.get("position") or {}).get("abbreviation"),
                    "jersey": athlete.get("jersey"),
                    "team_id": team_id, "team": team.get("displayName"),
                    "team_abbr": team.get("abbreviation"),
                    "opponent_id": opp_id, "opponent": opp,
                    "opponent_abbr": None, "home_away": home_away,
                    "player_group": group.get("name") or "",
                    "started": entry.get("starter"),
                    "active": entry.get("active"),
                }
                for name in spec.columns:
                    raw = stats.get(name)
                    if name in spec.splits:
                        made, att = made_attempted(raw)
                        row[f"{name}_made"], row[f"{name}_attempted"] = made, att
                    elif name in spec.clock:
                        row[name] = clock_minutes(raw)
                    else:
                        row[name] = number(raw)
                out.append(row)
    return out


def stat_columns(spec: SportSpec) -> list[str]:
    cols: list[str] = []
    for name in spec.columns:
        if name in spec.splits:
            cols += [f"{name}{s}" for s in _SPLIT_SUFFIXES]
        else:
            cols.append(name)
    return cols


# --- network + storage ---------------------------------------------------------------

def _get(session: requests.Session, path: str, endpoint: str, params: dict,
         retries: int = 3, pause: float = 0.4) -> dict:
    url = _BASE.format(path=path, endpoint=endpoint)
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, headers=_HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as exc:                       # noqa: BLE001
            last = exc
            time.sleep(pause * (attempt + 1))
    raise CollectorError(f"{path}/{endpoint} failed: {last}")


def fetch_schedule(spec: SportSpec, day: date, session: requests.Session | None = None
                   ) -> list[dict]:
    """Scheduled games for a date, unioning ESPN groups where the sport needs them."""
    own = session or requests.Session()
    token = day.strftime("%Y%m%d")
    variants = list(spec.groups) or [None]
    seen: dict[str, dict] = {}
    for group in variants:
        params: dict[str, Any] = {"dates": token, "limit": spec.limit}
        if group is not None:
            params["groups"] = group
        try:
            payload = _get(own, spec.espn_path, "scoreboard", params)
        except CollectorError:
            continue
        for event in payload.get("events") or []:
            game = parse_event(event)
            if game["game_id"]:
                seen.setdefault(game["game_id"], game)
    return sorted(seen.values(), key=lambda g: (g.get("start_time") or "", g["game_id"]))


def ensure_tables(conn: sqlite3.Connection, spec: SportSpec) -> None:
    games = f"{spec.table_prefix}_games"
    logs = f"{spec.table_prefix}_player_logs"
    conn.execute(f"""CREATE TABLE IF NOT EXISTS {games} (
        game_id TEXT PRIMARY KEY, game_date TEXT, start_time TEXT,
        season INTEGER, season_type INTEGER, status_name TEXT, is_completed INTEGER,
        home_team_id TEXT, home_team TEXT, home_score REAL,
        away_team_id TEXT, away_team TEXT, away_score REAL,
        venue TEXT, collected_at TEXT)""")
    cols = ", ".join(f'"{c}" REAL' for c in stat_columns(spec))
    conn.execute(f"""CREATE TABLE IF NOT EXISTS {logs} (
        game_id TEXT, game_date TEXT, season INTEGER, season_type INTEGER,
        player_id TEXT, player_name TEXT, position TEXT, jersey TEXT,
        team_id TEXT, team TEXT, team_abbr TEXT,
        opponent_id TEXT, opponent TEXT, opponent_abbr TEXT,
        home_away TEXT, player_group TEXT, started INTEGER, active INTEGER,
        {cols}, collected_at TEXT,
        PRIMARY KEY (game_id, player_id))""")


def _stored_game_ids(conn: sqlite3.Connection, spec: SportSpec) -> set[str]:
    """Games we already hold **player rows** for. Keyed on the logs table, not the games
    table: a game whose schedule row was written but whose box score failed must be
    retried, not skipped forever."""
    try:
        return {str(r[0]) for r in conn.execute(
            f"SELECT DISTINCT game_id FROM {spec.table_prefix}_player_logs")}
    except sqlite3.OperationalError:
        return set()


def collect(sport: str, start: date, end: date, db_path: str | Path = DB_PATH,
            *, force: bool = False, pause: float = 0.3,
            progress: bool = False) -> CollectionResult:
    """Collect player game logs for a date range. Incremental and safe to re-run."""
    if sport not in SPORTS:
        raise CollectorError(f"Unknown sport {sport!r}; known: {sorted(SPORTS)}")
    spec = SPORTS[sport]
    result = CollectionResult(sport=sport)
    session = requests.Session()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        ensure_tables(conn, spec)
        have = set() if force else _stored_game_ids(conn, spec)
        now = datetime.now(timezone.utc).isoformat()
        day = start
        while day <= end:
            games = fetch_schedule(spec, day, session)
            result.games_seen += len(games)
            for game in games:
                if not game["is_completed"]:
                    continue
                result.completed_games += 1
                if game["game_id"] in have:
                    result.skipped_existing += 1
                    continue
                try:
                    payload = _get(session, spec.espn_path, "summary",
                                   {"event": game["game_id"]})
                except CollectorError as exc:
                    result.failures.append(f"{game['game_id']}: {exc}")
                    continue
                rows = parse_player_rows(payload, game, spec)
                if not rows:
                    result.failures.append(f"{game['game_id']}: no player rows")
                    continue
                frame = pd.DataFrame(rows)
                frame["collected_at"] = now
                frame.to_sql(f"{spec.table_prefix}_player_logs", conn,
                             if_exists="append", index=False)
                g = {k: v for k, v in game.items()}
                g["collected_at"] = now
                pd.DataFrame([g]).to_sql(f"{spec.table_prefix}_games", conn,
                                         if_exists="append", index=False)
                result.games_downloaded += 1
                result.player_rows += len(rows)
                time.sleep(pause)
            if progress:
                print(f"  {day}  seen {result.games_seen}  new {result.games_downloaded}",
                      flush=True)
            day += timedelta(days=1)
    return result
