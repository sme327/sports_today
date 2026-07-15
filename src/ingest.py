from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd

from .config import DB_PATH

COLUMN_MAP = {
    "BIGDATABALL DATASET": "dataset",
    "GAME ID": "game_id",
    "DATE": "game_date",
    "INNING": "inning",
    "ROAD SCORE": "road_score",
    "HOME SCORE": "home_score",
    "BATTING TEAM": "batting_team",
    "BATTER": "batter_name",
    "BATTER MLB-ID": "batter_id",
    "BATTER HAND": "batter_hand",
    "RUNNERS ON BASE 1B": "runner_1b",
    "RUNNERS ON BASE 2B": "runner_2b",
    "RUNNERS ON BASE 3B": "runner_3b",
    "PITCHING TEAM": "pitching_team",
    "PITCHER": "pitcher_name",
    "PITCHER MLB-ID": "pitcher_id",
    "PITCHER HAND": "pitcher_hand",
    "C": "fielder_c",
    "1B": "fielder_1b",
    "2B": "fielder_2b",
    "3B": "fielder_3b",
    "SS": "fielder_ss",
    "LF": "fielder_lf",
    "CF": "fielder_cf",
    "RF": "fielder_rf",
    "PITCHING SEQUENCE LENGTH": "pitch_count_pa",
    "PITCH by PITCH S: Strike; Strike called; Strike swinging | B: Ball, called ball IN: In play | F: Foul; Foul ball on pitchout | FT: Foul tip; Foul tip on bunt | FB: Foul bunt IB: Intentional ball | HB: Hit batter | MB: Missed bunt attempt | NP: No pitch PO: Pitchout | POS: Swinging on pitchout | N-A: Unknown, Missed pitch | POF Pickoff thrown to 1B/2B/3B": "pitch_sequence",
    "HIT TYPE": "hit_type",
    "PLAY TYPE": "play_type",
    "RUNS": "runs_on_play",
    "OUTS": "outs_on_play",
    "STOLEN BASES": "stolen_bases",
    "CAUGHT STEALING": "caught_stealing",
    "DEFENSIVE INDIFFERENCE": "defensive_indifference",
    "PASSED BALL": "passed_ball",
    "WILD PITCH": "wild_pitch",
    "DESCRIPTION": "description",
}


def _clean_header(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\n", " ")).strip()


def _dedupe(names: Iterable[str]) -> list[str]:
    counts: dict[str, int] = {}
    out: list[str] = []
    for name in names:
        base = name or "unnamed"
        counts[base] = counts.get(base, 0) + 1
        out.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return out


def read_feed(path: str | Path) -> pd.DataFrame:
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Feed not found: {path}")

    raw = pd.read_excel(path, sheet_name=0, header=None)
    if raw.shape[0] < 3:
        raise ValueError("Workbook does not contain the expected two header rows plus data.")

    headers = _dedupe([_clean_header(v) for v in raw.iloc[1].tolist()])
    df = raw.iloc[2:].copy()
    df.columns = headers

    rename = {c: COLUMN_MAP.get(c, re.sub(r"[^a-z0-9]+", "_", c.lower()).strip("_")) for c in df.columns}
    df = df.rename(columns=rename)

    required = {
        "game_id", "game_date", "inning", "batting_team", "batter_name", "batter_id",
        "pitching_team", "pitcher_name", "pitcher_id", "play_type"
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce").dt.date.astype("string")
    for col in ["batter_id", "pitcher_id", "road_score", "home_score", "pitch_count_pa", "runs_on_play", "outs_on_play"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    text_cols = ["play_type", "hit_type", "batter_hand", "pitcher_hand", "pitch_sequence"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip()

    play = df["play_type"].fillna("").str.upper()
    df["is_hit"] = play.isin(["SINGLE", "DOUBLE", "TRIPLE", "HOME RUN"]).astype(int)
    df["total_bases"] = play.map({"SINGLE": 1, "DOUBLE": 2, "TRIPLE": 3, "HOME RUN": 4}).fillna(0).astype(int)
    df["is_walk"] = play.isin(["WALK", "INTENT WALK"]).astype(int)
    df["is_hbp"] = play.eq("HIT BY PITCH").astype(int)
    df["is_strikeout"] = play.eq("STRIKEOUT").astype(int)
    df["is_home_run"] = play.eq("HOME RUN").astype(int)
    df["is_official_ab"] = (~play.isin(["WALK", "INTENT WALK", "HIT BY PITCH", "SAC FLY", "SAC BUNT", "CATCHER INTERFERENCE"])).astype(int)
    df["reached_base"] = ((df["is_hit"] + df["is_walk"] + df["is_hbp"]) > 0).astype(int)
    df["has_risp"] = (df.get("runner_2b").notna() | df.get("runner_3b").notna()).astype(int)
    df["pa_number"] = df.groupby(["game_id", "batter_id"]).cumcount() + 1

    return df.reset_index(drop=True)


def write_database(df: pd.DataFrame, db_path: str | Path = DB_PATH) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        df.to_sql("plate_appearances", conn, if_exists="replace", index=False)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pa_game ON plate_appearances(game_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pa_date ON plate_appearances(game_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pa_batter ON plate_appearances(batter_id, game_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pa_pitcher ON plate_appearances(pitcher_id, game_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pa_teams ON plate_appearances(batting_team, pitching_team)")

        players = pd.concat([
            df[["batter_id", "batter_name"]].rename(columns={"batter_id": "player_id", "batter_name": "player_name"}),
            df[["pitcher_id", "pitcher_name"]].rename(columns={"pitcher_id": "player_id", "pitcher_name": "player_name"}),
        ]).dropna().drop_duplicates("player_id")
        players.to_sql("players", conn, if_exists="replace", index=False)

        games = df.groupby(["game_id", "game_date"], as_index=False).agg(
            road_team=("batting_team", "first"),
            pa_count=("game_id", "size"),
            final_road_score=("road_score", "max"),
            final_home_score=("home_score", "max"),
        )
        games.to_sql("games", conn, if_exists="replace", index=False)
    return db_path


def import_feed(path: str | Path, db_path: str | Path = DB_PATH) -> tuple[Path, dict[str, int]]:
    df = read_feed(path)
    db = write_database(df, db_path)
    summary = {
        "plate_appearances": len(df),
        "games": int(df["game_id"].nunique()),
        "batters": int(df["batter_id"].nunique()),
        "pitchers": int(df["pitcher_id"].nunique()),
    }
    return db, summary
