from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.config import DB_PATH


def load_wnba_player_game_logs(
    *,
    db_path: Path = DB_PATH,
    player_ids: Iterable[str] | None = None,
    team_ids: Iterable[str] | None = None,
    through_date: date | str | None = None,
) -> pd.DataFrame:
    clauses: list[str] = []
    parameters: list[object] = []

    if player_ids:
        values = [str(value) for value in player_ids]
        clauses.append(
            f"player_id IN ({','.join('?' for _ in values)})"
        )
        parameters.extend(values)

    if team_ids:
        values = [str(value) for value in team_ids]
        clauses.append(
            f"team_id IN ({','.join('?' for _ in values)})"
        )
        parameters.extend(values)

    if through_date is not None:
        value = (
            through_date.isoformat()
            if hasattr(through_date, "isoformat")
            else str(through_date)
        )
        clauses.append("substr(game_date, 1, 10) <= ?")
        parameters.append(value)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT *
        FROM wnba_player_game_logs
        {where}
        ORDER BY game_date, game_id, team, player_name
    """

    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(query, conn, params=parameters)


def recent_player_games(
    logs: pd.DataFrame,
    player_id: str,
    *,
    games: int = 10,
) -> pd.DataFrame:
    player = logs.loc[
        logs["player_id"].astype(str) == str(player_id)
    ].copy()
    if player.empty:
        return player
    player["game_date"] = pd.to_datetime(
        player["game_date"],
        utc=True,
        errors="coerce",
    )
    return (
        player.sort_values(["game_date", "game_id"], ascending=False)
        .head(games)
        .reset_index(drop=True)
    )


def player_recent_summary(
    logs: pd.DataFrame,
    *,
    windows: tuple[int, ...] = (5, 10, 20),
) -> pd.DataFrame:
    if logs.empty:
        return pd.DataFrame()

    data = logs.copy()
    data["game_date"] = pd.to_datetime(
        data["game_date"],
        utc=True,
        errors="coerce",
    )
    data = data.sort_values(
        ["player_id", "game_date", "game_id"],
        ascending=[True, False, False],
    )

    metrics = [
        "minutes",
        "points",
        "rebounds",
        "assists",
        "three_pointers_made",
        "field_goals_attempted",
        "three_pointers_attempted",
        "free_throws_attempted",
        "turnovers",
    ]

    rows: list[dict] = []
    for player_id, group in data.groupby("player_id", dropna=False):
        latest = group.iloc[0]
        row = {
            "player_id": str(player_id),
            "player_name": latest.get("player_name"),
            "team_id": latest.get("team_id"),
            "team": latest.get("team"),
            "team_abbr": latest.get("team_abbr"),
            "position": latest.get("position"),
            "headshot": latest.get("headshot"),
            "games_played": len(group),
            "starts": pd.to_numeric(
                group.get("started"),
                errors="coerce",
            ).fillna(0).sum(),
        }
        for window in windows:
            sample = group.head(window)
            row[f"games_l{window}"] = len(sample)
            for metric in metrics:
                values = pd.to_numeric(
                    sample.get(metric),
                    errors="coerce",
                )
                row[f"{metric}_avg_l{window}"] = values.mean()
                row[f"{metric}_sd_l{window}"] = values.std(ddof=0)
        rows.append(row)

    return pd.DataFrame(rows)


def threshold_history(
    logs: pd.DataFrame,
    *,
    player_id: str,
    metric: str,
    threshold: float,
    games: int = 10,
) -> dict:
    recent = recent_player_games(logs, player_id, games=games)
    if recent.empty or metric not in recent:
        return {
            "games": 0,
            "hits": 0,
            "hit_rate": None,
            "values": [],
        }

    values = pd.to_numeric(recent[metric], errors="coerce").dropna()
    hits = int((values >= threshold).sum())
    total = int(len(values))
    return {
        "games": total,
        "hits": hits,
        "hit_rate": hits / total if total else None,
        "values": values.tolist(),
    }
