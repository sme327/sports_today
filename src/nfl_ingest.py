"""NFL season feed ingest (Big Data Ball xlsx → SQLite), mirroring the MLB pattern.

Two workbooks per season — a **team** feed (one row per team per game) and a **player**
feed (one row per player per game) — plus a shared TEAMS dimension. Both use Big Data
Ball's multi-row category headers: the team feed has 2 header rows (category / field),
the player feed 3 (super-category / sub-category / field), with field names that repeat
across categories (YDS/TD/ATT under Passing, Rushing, Receiving…). We flatten those into
unique, readable column names (``passing_yds``, ``rushing_att``, ``receiving_rec`` …).

Full-season replace, like MLB: each ingest rebuilds the NFL tables in ``sportshub.db``.
The feed on hand (pulled 01-12) covers the regular season + Wild Card; re-download the
completed-season feed for the full playoffs + Super Bowl.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

from src.config import DB_PATH

# Header categories that are banners, not stat groups — their columns keep the bare
# field name (game_id, date, player…) with no prefix.
_BANNERS = {"game_info", "game_player_information"}

# A few field names cleaned nicer than their raw text.
_FIELD_RENAME = {
    "week": "week", "week_2": "week",
    "starter_y_n": "starter", "venue_r_h_n": "venue",
    "bigdataball_dataset": "dataset", "player_id": "player_id",
    "1_0": "q1", "2_0": "q2", "3_0": "q3", "4_0": "q4",   # quarter scores (headers read as floats)
    "1_downs_first_downs": "first_downs",
    "third_downs_third_down_s_made": "third_downs_made",
    "third_downs_third_down_s_attempted": "third_downs_att",
    "fourth_downs_fourth_down_s_made": "fourth_downs_made",
    "fourth_downs_fourth_down_s_attempted": "fourth_downs_att",
    "total_plays_total_plays": "total_plays",
    "possession_time_of_possession": "time_of_possession",
}

_REGULAR_SEASON_MAX_WEEK = 18   # weeks 1–18 regular season; 19+ = postseason


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"[^a-z0-9]+", "_", str(value).replace("\n", " ").lower()).strip("_")


def _dedupe(names: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    out: list[str] = []
    for name in names:
        base = name or "unnamed"
        counts[base] = counts.get(base, 0) + 1
        out.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return out


def _column_names(raw: pd.DataFrame, group_rows: list[int], field_row: int) -> list[str]:
    """Flatten multi-row category headers into unique, readable names.

    ``group_rows`` are header rows whose merged cells forward-fill to give each column a
    category (the most specific non-banner one becomes the prefix); ``field_row`` is the
    row with the actual field name."""
    groups = [[_clean(v) for v in raw.iloc[gr].ffill().tolist()] for gr in group_rows]
    fields = [_clean(v) for v in raw.iloc[field_row].tolist()]
    names: list[str] = []
    for i, field in enumerate(fields):
        parts = [g[i] for g in groups if g[i] and g[i] not in _BANNERS]
        prefix = parts[-1] if parts else ""
        name = f"{prefix}_{field}" if prefix else field
        names.append(_FIELD_RENAME.get(name, name))
    return _dedupe(names)


def _numeric_frame(raw: pd.DataFrame, names: list[str], first_data_row: int) -> pd.DataFrame:
    """Body rows with the flattened names; coerce every non-identity column to numeric."""
    df = raw.iloc[first_data_row:].copy()
    df.columns = names
    df = df.dropna(how="all").reset_index(drop=True)
    if "game_date" not in df.columns and "date" in df.columns:
        df = df.rename(columns={"date": "game_date"})
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce").dt.date.astype("string")
    identity = {"dataset", "game_id", "game_date", "team", "opponent", "venue", "starter",
                "player", "player_id", "position", "start_time_et"}
    for col in df.columns:
        if col not in identity:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "week" in df.columns:
        df["week"] = pd.to_numeric(df["week"], errors="coerce").astype("Int64")
        df["season_type"] = df["week"].map(
            lambda w: "regular" if pd.notna(w) and w <= _REGULAR_SEASON_MAX_WEEK else "postseason")
    for col in ("game_id", "team", "player", "player_id", "position", "opponent"):
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip()
    return df


def _pair_opponents(team_df: pd.DataFrame) -> pd.DataFrame:
    """Each game_id has exactly two team rows; set each row's opponent to the other."""
    opp: dict[tuple, str] = {}
    for gid, grp in team_df.groupby("game_id"):
        teams = grp["team"].tolist()
        if len(teams) == 2:
            opp[(gid, teams[0])], opp[(gid, teams[1])] = teams[1], teams[0]
    team_df["opponent"] = [opp.get((g, t)) for g, t in zip(team_df["game_id"], team_df["team"])]
    return team_df


def read_team_feed(path: str | Path) -> pd.DataFrame:
    raw = pd.read_excel(Path(path).expanduser(), sheet_name=0, header=None)
    names = _column_names(raw, group_rows=[0], field_row=1)
    return _pair_opponents(_numeric_frame(raw, names, first_data_row=2))


def read_player_feed(path: str | Path) -> pd.DataFrame:
    raw = pd.read_excel(Path(path).expanduser(), sheet_name=0, header=None)
    names = _column_names(raw, group_rows=[0, 1], field_row=2)
    return _numeric_frame(raw, names, first_data_row=3)


def read_teams(path: str | Path) -> pd.DataFrame:
    teams = pd.read_excel(Path(path).expanduser(), sheet_name="TEAMS")
    teams.columns = [_clean(c) for c in teams.columns]
    return teams.rename(columns={
        "bigdataball_initial": "initial", "nfl_com_initial": "nfl_initial",
        "team_long_name": "long_name", "team_short_name": "short_name",
        "team_nick_name": "nick_name",
    })


def write_database(team_df: pd.DataFrame, player_df: pd.DataFrame, teams_df: pd.DataFrame,
                   db_path: str | Path = DB_PATH) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        team_df.to_sql("nfl_team_games", conn, if_exists="replace", index=False)
        player_df.to_sql("nfl_player_games", conn, if_exists="replace", index=False)
        teams_df.to_sql("nfl_teams", conn, if_exists="replace", index=False)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nfl_tg_game ON nfl_team_games(game_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nfl_tg_team ON nfl_team_games(team, game_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nfl_pg_game ON nfl_player_games(game_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nfl_pg_player ON nfl_player_games(player_id, game_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nfl_pg_team ON nfl_player_games(team, game_date)")
    return db_path


def import_nfl_feeds(team_path: str | Path, player_path: str | Path,
                     db_path: str | Path = DB_PATH) -> dict[str, int]:
    """Ingest both NFL feeds into ``sportshub.db``. Returns row counts."""
    team_df = read_team_feed(team_path)
    player_df = read_player_feed(player_path)
    teams_df = read_teams(team_path)
    write_database(team_df, player_df, teams_df, db_path)
    return {
        "team_games": len(team_df),
        "player_games": len(player_df),
        "teams": len(teams_df),
        "games": team_df["game_id"].nunique(),
        "weeks": int(team_df["week"].max()) if team_df["week"].notna().any() else 0,
    }
