"""League-wide, evidence-backed MLB player trends for the public trends page."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from services.data_access import load_plate_appearances
from src.config import DB_PATH
from src.pitcher_opportunity import _per_start_lines

_ACTIVE_WITHIN_DAYS = 10


def _headshot(player_id: str) -> str:
    return ("https://img.mlbstatic.com/mlb-photos/image/upload/w_160,q_auto:best/"
            f"v1/people/{player_id}/headshot/67/current")


def _pct(value: float) -> str:
    return f"{value:.0%}"


def _row(*, player_id: str, name: str, team: str, sort: float,
         primary: str = "", unit: str = "", change: str = "",
         direction: str = "flat", baseline: str = "") -> dict:
    """One player's result, as numbers rather than a sentence.

    The section says what the metric is; a row only has to say who and how much. Every
    field is pre-formatted here so the template does no arithmetic and no phrasing —
    which is also what lets three different display types share one row shape.
    """
    return {"player_id": player_id, "name": name, "team": team,
            "headshot": _headshot(player_id), "sort": sort,
            "primary": primary, "unit": unit, "change": change,
            "direction": direction, "baseline": baseline}


def _batter_cards(pa: pd.DataFrame) -> dict[str, list[dict]]:
    required = {"batter_id", "batter_name", "batting_team", "game_id", "game_date",
                "is_hit", "is_strikeout"}
    if pa.empty or not required.issubset(pa.columns):
        return {"streaks": [], "hits": [], "batter_k": []}
    x = pa.copy()
    x["is_hit"] = pd.to_numeric(x["is_hit"], errors="coerce").fillna(0)
    x["is_strikeout"] = pd.to_numeric(x["is_strikeout"], errors="coerce").fillna(0)
    games = (x.groupby(["batter_id", "batter_name", "batting_team", "game_date", "game_id"],
                       dropna=False)
             .agg(hits=("is_hit", "sum"), strikeouts=("is_strikeout", "sum"),
                  pa=("is_hit", "size")).reset_index()
             .sort_values(["game_date", "game_id"]))
    hit_cards, k_cards, streak_cards = [], [], []
    latest_date = games["game_date"].max()
    for pid, group in games.groupby("batter_id"):
        group = group.sort_values(["game_date", "game_id"])
        if latest_date - group["game_date"].max() > pd.Timedelta(days=_ACTIVE_WITHIN_DAYS):
            continue
        if len(group) < 20:
            continue
        recent = group.tail(10)
        prior = group.iloc[:-10]
        if len(prior) < 10:
            continue
        name = str(group["batter_name"].iloc[-1])
        team = str(group["batting_team"].iloc[-1])

        streak = 0
        for has_hit in reversed((group["hits"] >= 1).tolist()):
            if not has_hit:
                break
            streak += 1
        if streak >= 6:
            streak_cards.append(_row(
                player_id=str(pid), name=name, team=team, sort=float(streak),
                primary=str(streak), unit="games", direction="up"))

        recent_hit = float((recent["hits"] >= 1).mean())
        prior_hit = float((prior["hits"] >= 1).mean())
        hit_delta = recent_hit - prior_hit
        if abs(hit_delta) >= .12:
            hit_cards.append(_row(
                player_id=str(pid), name=name, team=team, sort=abs(hit_delta),
                primary=f"{int((recent['hits'] >= 1).sum())} of 10",
                change=f"{hit_delta * 100:+.0f}pp",
                direction="up" if hit_delta > 0 else "down",
                baseline=_pct(prior_hit)))

        recent_k2 = float((recent["strikeouts"] >= 2).mean())
        prior_k2 = float((prior["strikeouts"] >= 2).mean())
        k_delta = recent_k2 - prior_k2
        if abs(k_delta) >= .12:
            # More strikeouts is a worse result, so the arrow follows the *number* and
            # the colour follows the outcome — a rise in multi-K games reads "down".
            k_cards.append(_row(
                player_id=str(pid), name=name, team=team, sort=abs(k_delta),
                primary=f"{int((recent['strikeouts'] >= 2).sum())} of 10",
                change=f"{k_delta * 100:+.0f}pp",
                direction="down" if k_delta > 0 else "up",
                baseline=_pct(prior_k2)))
    by_sort = lambda rows, n: sorted(rows, key=lambda c: c["sort"], reverse=True)[:n]
    return {"streaks": by_sort(streak_cards, 4), "hits": by_sort(hit_cards, 6),
            "batter_k": by_sort(k_cards, 6)}


def _pitcher_cards(pa: pd.DataFrame) -> list[dict]:
    required = {"pitcher_id", "pitcher_name", "pitching_team", "game_id", "game_date",
                "inning", "is_strikeout", "is_hit"}
    if pa.empty or not required.issubset(pa.columns):
        return []
    cards = []
    latest_date = pd.to_datetime(pa["game_date"]).max()
    for pid, group in pa.groupby("pitcher_id"):
        if latest_date - pd.to_datetime(group["game_date"]).max() > pd.Timedelta(days=_ACTIVE_WITHIN_DAYS):
            continue
        lines = _per_start_lines(group)
        if len(lines) < 8:
            continue
        recent, prior = lines.head(5), lines.iloc[5:10]
        if len(prior) < 3:
            continue
        recent_avg, prior_avg = float(recent["k"].mean()), float(prior["k"].mean())
        delta = recent_avg - prior_avg
        if abs(delta) < 1.0:
            continue
        name = str(group.sort_values("game_date")["pitcher_name"].iloc[-1])
        team = str(group.sort_values("game_date")["pitching_team"].iloc[-1])
        cards.append(_row(
            player_id=str(pid), name=name, team=team, sort=abs(delta),
            primary=f"{recent_avg:.1f}", unit="K/start",
            change=f"{delta:+.1f}", direction="up" if delta > 0 else "down",
            baseline=f"{prior_avg:.1f}"))
    return sorted(cards, key=lambda c: c["sort"], reverse=True)[:6]


def build_context(as_of: date | None = None, db_path: Path = DB_PATH) -> dict:
    today = as_of or date.today()
    # load_plate_appearances is exclusive; tomorrow includes every completed row through
    # the selected day while retaining the project's leakage-safe date boundary.
    pa = load_plate_appearances(as_of=today + timedelta(days=1), db_path=db_path)
    batter = _batter_cards(pa)
    sections = [
        {"slug": "streaks", "display": "streak",
         "title": "Active Hit Streaks", "subtitle": "Longest current hit streaks",
         "nav": "Active Hit Streaks", "context": "",
         "columns": (), "rows": batter["streaks"]},
        {"slug": "hits", "display": "comparison",
         "title": "Better Hits", "subtitle": "More hits than earlier in the season",
         "nav": "Better Hits", "context": "Last 10 games vs earlier sample",
         "columns": ("Hits in last 10", "Change", "Before"), "rows": batter["hits"]},
        {"slug": "batter-k", "display": "comparison",
         "title": "Batter Strikeouts", "subtitle": "More multi-K games than earlier",
         "nav": "More Strikeouts", "context": "Last 10 games vs earlier sample",
         "columns": ("2+ K games in last 10", "Change", "Before"),
         "rows": batter["batter_k"]},
        {"slug": "pitcher-k", "display": "tile",
         "title": "Pitcher Strikeouts", "subtitle": "Strikeouts per start over last 5",
         "nav": "Pitcher Strikeouts", "context": "Last 5 starts vs prior 5",
         "columns": (), "rows": _pitcher_cards(pa)},
    ]
    through = pa["game_date"].max().date() if not pa.empty else None
    return {"section": "trending", "league": "MLB", "sections": sections,
            "through": through, "has_data": any(s["rows"] for s in sections)}
