from __future__ import annotations

import sqlite3
from pathlib import Path
import pandas as pd

from .config import DB_PATH


def load_pa(db_path: str | Path = DB_PATH) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query("SELECT * FROM plate_appearances", conn)
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df


def hitter_summary(pa: pd.DataFrame, batter_id: int, last_pa: int = 50) -> dict:
    x = pa.loc[pa["batter_id"] == batter_id].sort_values(["game_date", "game_id", "pa_number"]).tail(last_pa)
    if x.empty:
        return {}
    ab = max(int(x["is_official_ab"].sum()), 1)
    return {
        "player": x["batter_name"].iloc[-1],
        "pa": len(x),
        "games": int(x["game_id"].nunique()),
        "hits": int(x["is_hit"].sum()),
        "total_bases": int(x["total_bases"].sum()),
        "walks": int(x["is_walk"].sum()),
        "strikeouts": int(x["is_strikeout"].sum()),
        "home_runs": int(x["is_home_run"].sum()),
        "avg": float(x["is_hit"].sum() / ab),
        "obp_proxy": float(x["reached_base"].mean()),
        "k_rate": float(x["is_strikeout"].mean()),
        "bb_rate": float(x["is_walk"].mean()),
        "pitches_per_pa": float(x["pitch_count_pa"].mean()),
        "risp_pa": int(x["has_risp"].sum()),
    }


def hitter_game_logs(pa: pd.DataFrame, batter_id: int, last_games: int = 10) -> pd.DataFrame:
    x = pa.loc[pa["batter_id"] == batter_id].copy()
    if x.empty:
        return pd.DataFrame()
    g = x.groupby(["game_date", "game_id", "batting_team", "pitching_team"], as_index=False).agg(
        pa=("game_id", "size"), hits=("is_hit", "sum"), total_bases=("total_bases", "sum"),
        walks=("is_walk", "sum"), strikeouts=("is_strikeout", "sum"), home_runs=("is_home_run", "sum")
    )
    return g.sort_values("game_date", ascending=False).head(last_games)


def team_recent(pa: pd.DataFrame, team: str, last_games: int = 10) -> dict:
    batting = pa.loc[pa["batting_team"] == team].copy()
    if batting.empty:
        return {}
    game_ids = batting.groupby("game_id")["game_date"].max().sort_values(ascending=False).head(last_games).index
    x = batting.loc[batting["game_id"].isin(game_ids)]
    return {
        "team": team,
        "games": int(x["game_id"].nunique()),
        "pa_per_game": float(len(x) / max(x["game_id"].nunique(), 1)),
        "hits_per_game": float(x["is_hit"].sum() / max(x["game_id"].nunique(), 1)),
        "tb_per_game": float(x["total_bases"].sum() / max(x["game_id"].nunique(), 1)),
        "k_rate": float(x["is_strikeout"].mean()),
        "bb_rate": float(x["is_walk"].mean()),
        "pitches_per_pa": float(x["pitch_count_pa"].mean()),
    }
