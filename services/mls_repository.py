"""Leakage-safe reads over the collected MLS team-match data (Phase 3B).

Every query is bounded by the matchup date ``D``: it includes only completed
matches **strictly before** ``D``, excludes the selected match, and never sees a
match on/after ``D``. All page analytics read here, never raw ESPN responses.

Pure (Streamlit-free); opens its own SQLite connection. Aggregates report their
sample size so the builder can express honest confidence.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from src.config import DB_PATH

# Metrics carried on each team-match row (own perspective).
_OWN = [
    "goals_for", "goals_against", "total_shots", "shots_on_target", "shot_pct",
    "blocked_shots", "won_corners", "fouls_committed", "offsides", "saves",
    "yellow_cards", "red_cards", "total_passes", "accurate_passes", "pass_pct",
    "total_crosses", "accurate_crosses", "cross_pct", "total_tackles",
    "interceptions", "total_clearances", "pk_goals", "pk_shots", "possession_pct",
]


def _connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def team_match_frame(as_of: date, *, exclude_event_id: str | None = None,
                     db_path: Path = DB_PATH) -> pd.DataFrame:
    """All team-match rows strictly before ``as_of`` (leakage-safe), one row per
    team per match, enriched with the opponent's shots faced. Empty frame if the
    MLS tables are absent or empty."""
    try:
        with _connect(db_path) as conn:
            stats = pd.read_sql_query(
                "SELECT s.*, m.match_date FROM mls_team_match_stats s "
                "JOIN mls_matches m ON m.event_id = s.event_id "
                "WHERE m.match_date < ?",
                conn, params=(as_of.isoformat(),),
            )
    except Exception:
        return pd.DataFrame()
    if stats.empty:
        return stats
    if exclude_event_id is not None:
        stats = stats[stats["event_id"].astype(str) != str(exclude_event_id)]
    if stats.empty:
        return stats

    # Merge opponent shots (defensive shot pressure faced) via the paired row.
    opp = stats[["event_id", "team_id", "total_shots", "shots_on_target"]].rename(
        columns={"team_id": "opponent_id", "total_shots": "shots_faced",
                 "shots_on_target": "sot_faced"})
    merged = stats.merge(opp, on=["event_id", "opponent_id"], how="left")
    return merged


def _result(row) -> str:
    if row.goals_for > row.goals_against:
        return "W"
    if row.goals_for < row.goals_against:
        return "L"
    return "D"


def _venue_filter(frame: pd.DataFrame, venue: str | None) -> pd.DataFrame:
    if venue == "home":
        return frame[frame["is_home"] == 1]
    if venue == "away":
        return frame[frame["is_home"] == 0]
    return frame


def team_aggregate(frame: pd.DataFrame, team_id: str, *, venue: str | None = None,
                   last_n: int | None = None) -> dict:
    """Per-match aggregates for a team. Counts/possession use simple means;
    accuracy rates use pooled ratios (sum/sum) — see the engineering doc. Returns
    ``{"matches": n, ...}``; an empty selection yields ``matches=0``."""
    if frame.empty:
        return {"matches": 0}
    sub = frame[frame["team_id"].astype(str) == str(team_id)]
    sub = _venue_filter(sub, venue).sort_values("match_date")
    if last_n:
        sub = sub.tail(last_n)
    n = len(sub)
    if n == 0:
        return {"matches": 0}

    def mean(col):
        v = sub[col].dropna()
        return float(v.mean()) if len(v) else None

    def ratio(num, den):
        a, b = sub[num].dropna().sum(), sub[den].dropna().sum()
        return round(100.0 * a / b, 1) if b else None

    results = [_result(r) for r in sub.itertuples()]
    wins, draws, losses = results.count("W"), results.count("D"), results.count("L")
    points = 3 * wins + draws

    return {
        "matches": n,
        "wins": wins, "draws": draws, "losses": losses,
        "points": points, "ppm": round(points / n, 2) if n else None,
        "goals_for": mean("goals_for"),
        "goals_against": mean("goals_against"),
        "goal_diff": (mean("goals_for") - mean("goals_against"))
        if mean("goals_for") is not None and mean("goals_against") is not None else None,
        "shots": mean("total_shots"),
        "shots_on_target": mean("shots_on_target"),
        "shot_accuracy": ratio("shots_on_target", "total_shots"),
        "possession": mean("possession_pct"),
        "pass_completion": ratio("accurate_passes", "total_passes"),
        "corners": mean("won_corners"),
        "crosses": mean("total_crosses"),
        "cross_accuracy": ratio("accurate_crosses", "total_crosses"),
        "fouls": mean("fouls_committed"),
        "yellows": mean("yellow_cards"),
        "pk_attempts": mean("pk_shots"),           # penalty attempts per match
        "reds_total": int(sub["red_cards"].dropna().sum()),
        "tackles": mean("total_tackles"),
        "interceptions": mean("interceptions"),
        "blocked_shots": mean("blocked_shots"),
        "saves": mean("saves"),
        "shots_faced": mean("shots_faced"),
        "sot_faced": mean("sot_faced"),
    }


def recent_results(frame: pd.DataFrame, team_id: str, *, n: int = 5,
                   venue: str | None = None) -> dict:
    """Last-``n`` regular-season results (most recent last) with goals context."""
    if frame.empty:
        return {"matches": 0, "form": (), "goals_for": None, "goals_against": None}
    sub = frame[frame["team_id"].astype(str) == str(team_id)]
    sub = _venue_filter(sub, venue).sort_values("match_date").tail(n)
    if sub.empty:
        return {"matches": 0, "form": (), "goals_for": None, "goals_against": None}
    form = tuple(_result(r) for r in sub.itertuples())
    return {
        "matches": len(sub),
        "form": form,
        "wins": form.count("W"), "draws": form.count("D"), "losses": form.count("L"),
        "goals_for": float(sub["goals_for"].mean()),
        "goals_against": float(sub["goals_against"].mean()),
        "shots": float(sub["total_shots"].mean()),
        "shots_on_target": float(sub["shots_on_target"].mean()),
        "unbeaten": form.count("L") == 0,
        "winless": form.count("W") == 0,
    }


def league_averages(frame: pd.DataFrame) -> dict:
    """League-wide per-match means (context for 'above/below average')."""
    if frame.empty:
        return {"matches": 0}
    def mean(col):
        v = frame[col].dropna()
        return float(v.mean()) if len(v) else None
    return {
        "matches": len(frame),
        "goals_for": mean("goals_for"),
        "shots": mean("total_shots"),
        "shots_on_target": mean("shots_on_target"),
        "possession": mean("possession_pct"),
        "pass_completion": round(100.0 * frame["accurate_passes"].sum() / frame["total_passes"].sum(), 1)
        if frame["total_passes"].sum() else None,
        "corners": mean("won_corners"),
        "crosses": mean("total_crosses"),
        "fouls": mean("fouls_committed"),
        "yellows": mean("yellow_cards"),
        "shots_faced": mean("shots_faced"),
    }


def standings_lookup(team_id: str, as_of: date, *, season: int = 2026,
                     db_path: Path = DB_PATH) -> dict | None:
    """Latest standings snapshot on/before ``as_of`` for a team, else the latest
    available. Returns None if standings were never collected."""
    try:
        with _connect(db_path) as conn:
            df = pd.read_sql_query(
                "SELECT * FROM mls_standings WHERE team_id = ? AND season = ?",
                conn, params=(str(team_id), season))
    except Exception:
        return None
    if df.empty:
        return None
    bounded = df[df["snapshot_date"] <= as_of.isoformat()]
    pick = bounded if not bounded.empty else df
    row = pick.sort_values("snapshot_date").iloc[-1]
    return {k: (None if pd.isna(row[k]) else row[k]) for k in row.index}


def has_team_data(as_of: date, *, db_path: Path = DB_PATH) -> bool:
    return not team_match_frame(as_of, db_path=db_path).empty
