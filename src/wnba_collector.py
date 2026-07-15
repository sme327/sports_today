from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

from src.config import DATABASE_DIR, DATA_DIR

SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/"
    "basketball/wnba/scoreboard"
)
SUMMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/"
    "basketball/wnba/summary"
)

WNBA_DATA_DIR = DATA_DIR / "wnba"
WNBA_GAMES_CSV = WNBA_DATA_DIR / "wnba_games.csv"
WNBA_PLAYER_LOGS_CSV = WNBA_DATA_DIR / "wnba_player_game_logs.csv"
WNBA_DB_PATH = DATABASE_DIR / "sportshub.db"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 SportsHub/1.0"
    ),
    "Accept": "application/json,text/plain,*/*",
}


class WNBACollectorError(RuntimeError):
    """Raised when the WNBA source cannot be collected or parsed safely."""


@dataclass(frozen=True)
class CollectionResult:
    games_seen: int
    completed_games: int
    games_downloaded: int
    player_rows_written: int
    skipped_existing_games: int
    database_path: Path
    games_csv: Path
    player_logs_csv: Path


def _request_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any],
    timeout: int = 30,
    retries: int = 3,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise WNBACollectorError(
                    f"Unexpected non-object JSON from {response.url}"
                )
            return payload
        except (requests.RequestException, ValueError, WNBACollectorError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.25 * attempt)
    raise WNBACollectorError(
        f"WNBA request failed after {retries} attempts: {last_error}"
    )


def _team_logo(team: dict[str, Any]) -> str | None:
    logos = team.get("logos") or []
    if logos and isinstance(logos[0], dict):
        return logos[0].get("href")
    return None


def _parse_event(event: dict[str, Any]) -> dict[str, Any]:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors") or []
    home = next(
        (c for c in competitors if c.get("homeAway") == "home"),
        {},
    )
    away = next(
        (c for c in competitors if c.get("homeAway") == "away"),
        {},
    )
    home_team = home.get("team") or {}
    away_team = away.get("team") or {}
    status = event.get("status", {}).get("type", {})

    broadcasts: list[str] = []
    for item in competition.get("broadcasts") or []:
        broadcasts.extend(item.get("names") or [])

    return {
        "game_id": str(event.get("id") or ""),
        "game_date": event.get("date"),
        "season": event.get("season", {}).get("year"),
        "season_type": event.get("season", {}).get("type"),
        "status_name": status.get("name"),
        "status_detail": status.get("detail")
        or status.get("description"),
        "is_completed": bool(status.get("completed")),
        "home_team_id": str(home_team.get("id") or ""),
        "home_team": home_team.get("displayName"),
        "home_abbr": home_team.get("abbreviation"),
        "home_logo": _team_logo(home_team),
        "home_score": pd.to_numeric(home.get("score"), errors="coerce"),
        "away_team_id": str(away_team.get("id") or ""),
        "away_team": away_team.get("displayName"),
        "away_abbr": away_team.get("abbreviation"),
        "away_logo": _team_logo(away_team),
        "away_score": pd.to_numeric(away.get("score"), errors="coerce"),
        "venue": competition.get("venue", {}).get("fullName"),
        "broadcast": ", ".join(dict.fromkeys(broadcasts)),
    }


def fetch_schedule_date(
    game_date: date,
    *,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    owned_session = session is None
    session = session or requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    try:
        payload = _request_json(
            session,
            SCOREBOARD_URL,
            params={"dates": game_date.strftime("%Y%m%d"), "limit": 100},
        )
        return [_parse_event(event) for event in payload.get("events", [])]
    finally:
        if owned_session:
            session.close()


def fetch_schedule_range(
    start_date: date,
    end_date: date,
    *,
    session: requests.Session | None = None,
    pause_seconds: float = 0.08,
) -> list[dict[str, Any]]:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    owned_session = session is None
    session = session or requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    games: dict[str, dict[str, Any]] = {}
    try:
        current = start_date
        while current <= end_date:
            for game in fetch_schedule_date(current, session=session):
                if game["game_id"]:
                    games[game["game_id"]] = game
            current += timedelta(days=1)
            if pause_seconds:
                time.sleep(pause_seconds)
    finally:
        if owned_session:
            session.close()
    return sorted(games.values(), key=lambda row: row.get("game_date") or "")


STAT_ALIASES = {
    "min": "minutes",
    "minutes": "minutes",
    "fg": "field_goals",
    "fieldgoals": "field_goals",
    "3pt": "three_pointers",
    "3p": "three_pointers",
    "threepointfieldgoals": "three_pointers",
    "ft": "free_throws",
    "freethrows": "free_throws",
    "oreb": "offensive_rebounds",
    "offensiverebounds": "offensive_rebounds",
    "dreb": "defensive_rebounds",
    "defensiverebounds": "defensive_rebounds",
    "reb": "rebounds",
    "totalrebounds": "rebounds",
    "ast": "assists",
    "assists": "assists",
    "stl": "steals",
    "steals": "steals",
    "blk": "blocks",
    "blocks": "blocks",
    "to": "turnovers",
    "turnovers": "turnovers",
    "pf": "personal_fouls",
    "fouls": "personal_fouls",
    "+/-": "plus_minus",
    "plusminus": "plus_minus",
    "pts": "points",
    "points": "points",
}


def _clean_stat_name(value: object) -> str:
    raw = str(value or "").strip().lower()
    compact = re_sub_non_alnum(raw)
    return STAT_ALIASES.get(raw) or STAT_ALIASES.get(compact) or compact


def re_sub_non_alnum(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in {"+", "-", "/"})


def _number(value: object) -> float | None:
    if value in (None, "", "--", "DNP", "N/A"):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _made_attempted(value: object) -> tuple[float | None, float | None]:
    if value in (None, "", "--"):
        return None, None
    text = str(value).strip()
    for separator in ("-", "/"):
        if separator in text:
            left, right = text.split(separator, 1)
            return _number(left), _number(right)
    return _number(value), None


def _minutes_float(value: object) -> float | None:
    if value in (None, "", "--", "DNP"):
        return None
    text = str(value).strip()
    if ":" in text:
        minutes, seconds = text.split(":", 1)
        try:
            return float(minutes) + float(seconds) / 60.0
        except ValueError:
            return None
    return _number(value)


def _athlete_id(athlete: dict[str, Any]) -> str:
    return str(athlete.get("id") or athlete.get("uid") or "")


def _parse_player_entry(
    *,
    game: dict[str, Any],
    team: dict[str, Any],
    opponent: dict[str, Any],
    home_away: str,
    athlete: dict[str, Any],
    labels: list[str],
    values: list[Any],
    starter: bool | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    stats = {
        _clean_stat_name(label): value
        for label, value in zip(labels, values)
    }

    fg_made, fg_attempted = _made_attempted(stats.get("field_goals"))
    three_made, three_attempted = _made_attempted(stats.get("three_pointers"))
    ft_made, ft_attempted = _made_attempted(stats.get("free_throws"))

    return {
        "game_id": game["game_id"],
        "game_date": game["game_date"],
        "season": game["season"],
        "season_type": game["season_type"],
        "player_id": _athlete_id(athlete),
        "player_name": athlete.get("displayName")
        or athlete.get("shortName")
        or athlete.get("fullName"),
        "short_name": athlete.get("shortName"),
        "position": (athlete.get("position") or {}).get("abbreviation"),
        "jersey": athlete.get("jersey"),
        "headshot": (athlete.get("headshot") or {}).get("href"),
        "team_id": str(team.get("id") or ""),
        "team": team.get("displayName"),
        "team_abbr": team.get("abbreviation"),
        "opponent_id": str(opponent.get("id") or ""),
        "opponent": opponent.get("displayName"),
        "opponent_abbr": opponent.get("abbreviation"),
        "home_away": home_away,
        "started": bool(starter) if starter is not None else None,
        "active": bool(active) if active is not None else None,
        "minutes": _minutes_float(stats.get("minutes")),
        "field_goals_made": fg_made,
        "field_goals_attempted": fg_attempted,
        "three_pointers_made": three_made,
        "three_pointers_attempted": three_attempted,
        "free_throws_made": ft_made,
        "free_throws_attempted": ft_attempted,
        "offensive_rebounds": _number(stats.get("offensive_rebounds")),
        "defensive_rebounds": _number(stats.get("defensive_rebounds")),
        "rebounds": _number(stats.get("rebounds")),
        "assists": _number(stats.get("assists")),
        "steals": _number(stats.get("steals")),
        "blocks": _number(stats.get("blocks")),
        "turnovers": _number(stats.get("turnovers")),
        "personal_fouls": _number(stats.get("personal_fouls")),
        "plus_minus": _number(stats.get("plus_minus")),
        "points": _number(stats.get("points")),
    }


def _parse_boxscore_players(
    payload: dict[str, Any],
    game: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    players_sections = payload.get("boxscore", {}).get("players") or []

    for team_section in players_sections:
        team = team_section.get("team") or {}
        team_id = str(team.get("id") or "")
        home_away = (
            "home" if team_id == game["home_team_id"]
            else "away" if team_id == game["away_team_id"]
            else ""
        )
        opponent = {
            "id": (
                game["away_team_id"]
                if home_away == "home"
                else game["home_team_id"]
            ),
            "displayName": (
                game["away_team"]
                if home_away == "home"
                else game["home_team"]
            ),
            "abbreviation": (
                game["away_abbr"]
                if home_away == "home"
                else game["home_abbr"]
            ),
        }

        for statistics in team_section.get("statistics") or []:
            labels = statistics.get("labels") or []
            for athlete_entry in statistics.get("athletes") or []:
                athlete = athlete_entry.get("athlete") or {}
                rows.append(
                    _parse_player_entry(
                        game=game,
                        team=team,
                        opponent=opponent,
                        home_away=home_away,
                        athlete=athlete,
                        labels=labels,
                        values=athlete_entry.get("stats") or [],
                        starter=athlete_entry.get("starter"),
                        active=athlete_entry.get("active"),
                    )
                )
    return rows


def fetch_game_player_logs(
    game: dict[str, Any],
    *,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    game_id = game.get("game_id")
    if not game_id:
        raise ValueError("game must include game_id")

    owned_session = session is None
    session = session or requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    try:
        payload = _request_json(
            session,
            SUMMARY_URL,
            params={"event": game_id},
        )
        rows = _parse_boxscore_players(payload, game)
        if not rows:
            raise WNBACollectorError(
                f"No WNBA player box score rows found for game {game_id}"
            )
        return rows
    finally:
        if owned_session:
            session.close()


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS wnba_games (
            game_id TEXT PRIMARY KEY,
            game_date TEXT,
            season INTEGER,
            season_type INTEGER,
            status_name TEXT,
            status_detail TEXT,
            is_completed INTEGER,
            home_team_id TEXT,
            home_team TEXT,
            home_abbr TEXT,
            home_logo TEXT,
            home_score REAL,
            away_team_id TEXT,
            away_team TEXT,
            away_abbr TEXT,
            away_logo TEXT,
            away_score REAL,
            venue TEXT,
            broadcast TEXT,
            collected_at TEXT
        );

        CREATE TABLE IF NOT EXISTS wnba_player_game_logs (
            game_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            game_date TEXT,
            season INTEGER,
            season_type INTEGER,
            player_name TEXT,
            short_name TEXT,
            position TEXT,
            jersey TEXT,
            headshot TEXT,
            team_id TEXT,
            team TEXT,
            team_abbr TEXT,
            opponent_id TEXT,
            opponent TEXT,
            opponent_abbr TEXT,
            home_away TEXT,
            started INTEGER,
            active INTEGER,
            minutes REAL,
            field_goals_made REAL,
            field_goals_attempted REAL,
            three_pointers_made REAL,
            three_pointers_attempted REAL,
            free_throws_made REAL,
            free_throws_attempted REAL,
            offensive_rebounds REAL,
            defensive_rebounds REAL,
            rebounds REAL,
            assists REAL,
            steals REAL,
            blocks REAL,
            turnovers REAL,
            personal_fouls REAL,
            plus_minus REAL,
            points REAL,
            collected_at TEXT,
            PRIMARY KEY (game_id, player_id)
        );

        CREATE INDEX IF NOT EXISTS idx_wnba_logs_player_date
        ON wnba_player_game_logs(player_id, game_date);

        CREATE INDEX IF NOT EXISTS idx_wnba_logs_team_date
        ON wnba_player_game_logs(team_id, game_date);

        CREATE INDEX IF NOT EXISTS idx_wnba_logs_game
        ON wnba_player_game_logs(game_id);

        CREATE TABLE IF NOT EXISTS wnba_collection_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            finished_at TEXT,
            season INTEGER,
            start_date TEXT,
            end_date TEXT,
            games_seen INTEGER,
            completed_games INTEGER,
            games_downloaded INTEGER,
            player_rows_written INTEGER,
            skipped_existing_games INTEGER,
            status TEXT,
            message TEXT
        );
        """
    )


def _existing_completed_game_ids(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT game_id
        FROM wnba_player_game_logs
        """
    ).fetchall()
    return {str(row[0]) for row in rows}


def _upsert_dataframe(
    conn: sqlite3.Connection,
    table: str,
    frame: pd.DataFrame,
    key_columns: list[str],
) -> int:
    if frame.empty:
        return 0
    columns = list(frame.columns)
    placeholders = ", ".join("?" for _ in columns)
    quoted = ", ".join(f'"{column}"' for column in columns)
    updates = ", ".join(
        f'"{column}"=excluded."{column}"'
        for column in columns
        if column not in key_columns
    )
    conflict = ", ".join(f'"{column}"' for column in key_columns)
    sql = (
        f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders}) '
        f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
    )
    values = [
        tuple(None if pd.isna(value) else value for value in row)
        for row in frame.itertuples(index=False, name=None)
    ]
    conn.executemany(sql, values)
    return len(values)


def _write_csv_exports(conn: sqlite3.Connection) -> None:
    WNBA_DATA_DIR.mkdir(parents=True, exist_ok=True)
    games = pd.read_sql_query(
        "SELECT * FROM wnba_games ORDER BY game_date, game_id",
        conn,
    )
    logs = pd.read_sql_query(
        """
        SELECT *
        FROM wnba_player_game_logs
        ORDER BY game_date, game_id, team, player_name
        """,
        conn,
    )
    games.to_csv(WNBA_GAMES_CSV, index=False)
    logs.to_csv(WNBA_PLAYER_LOGS_CSV, index=False)


def collect_wnba_season(
    *,
    season: int,
    start_date: date | None = None,
    end_date: date | None = None,
    db_path: Path = WNBA_DB_PATH,
    force: bool = False,
    include_today_incomplete: bool = False,
    pause_seconds: float = 0.12,
) -> CollectionResult:
    start_date = start_date or date(season, 5, 1)
    end_date = end_date or date.today()
    started_at = datetime.now(timezone.utc).isoformat()
    collected_at = datetime.now(timezone.utc).isoformat()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    WNBA_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        _ensure_tables(conn)
        existing = _existing_completed_game_ids(conn)

        games = fetch_schedule_range(
            start_date,
            end_date,
            pause_seconds=pause_seconds,
        )
        game_frame = pd.DataFrame(games)
        if not game_frame.empty:
            game_frame["collected_at"] = collected_at
            game_frame["is_completed"] = (
                game_frame["is_completed"].fillna(False).astype(int)
            )
            _upsert_dataframe(conn, "wnba_games", game_frame, ["game_id"])

        eligible = [
            game for game in games
            if game.get("is_completed")
            or (
                include_today_incomplete
                and str(game.get("game_date", ""))[:10] == date.today().isoformat()
            )
        ]

        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        downloaded = 0
        skipped = 0
        written = 0
        try:
            for game in eligible:
                game_id = str(game["game_id"])
                if game_id in existing and not force:
                    skipped += 1
                    continue
                rows = fetch_game_player_logs(game, session=session)
                frame = pd.DataFrame(rows)
                if frame.empty:
                    continue
                frame["collected_at"] = collected_at
                for bool_col in ("started", "active"):
                    frame[bool_col] = frame[bool_col].map(
                        lambda value: None if pd.isna(value) else int(bool(value))
                    )
                written += _upsert_dataframe(
                    conn,
                    "wnba_player_game_logs",
                    frame,
                    ["game_id", "player_id"],
                )
                downloaded += 1
                if pause_seconds:
                    time.sleep(pause_seconds)
        finally:
            session.close()

        _write_csv_exports(conn)
        finished_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO wnba_collection_runs (
                started_at, finished_at, season, start_date, end_date,
                games_seen, completed_games, games_downloaded,
                player_rows_written, skipped_existing_games, status, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                started_at,
                finished_at,
                season,
                start_date.isoformat(),
                end_date.isoformat(),
                len(games),
                sum(bool(game.get("is_completed")) for game in games),
                downloaded,
                written,
                skipped,
                "SUCCESS",
                "WNBA schedule and player game logs collected.",
            ),
        )
        conn.commit()

    return CollectionResult(
        games_seen=len(games),
        completed_games=sum(bool(game.get("is_completed")) for game in games),
        games_downloaded=downloaded,
        player_rows_written=written,
        skipped_existing_games=skipped,
        database_path=db_path,
        games_csv=WNBA_GAMES_CSV,
        player_logs_csv=WNBA_PLAYER_LOGS_CSV,
    )
