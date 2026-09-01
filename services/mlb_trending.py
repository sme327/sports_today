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


def _card(*, market: str, icon: str, player_id: str, name: str, team: str,
          headline: str, detail: str, tone: str, value: float) -> dict:
    return {"market": market, "icon": icon, "player_id": player_id, "name": name,
            "team": team, "headshot": _headshot(player_id), "headline": headline,
            "detail": detail, "tone": tone, "value": value}


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
            streak_cards.append(_card(
                market="Active hit streak", icon="🔥", player_id=str(pid), name=name,
                team=team, headline=f"A hit in {streak} straight games",
                detail="An active game-by-game streak through his latest appearance",
                tone="up", value=float(streak)))

        recent_hit = float((recent["hits"] >= 1).mean())
        prior_hit = float((prior["hits"] >= 1).mean())
        hit_delta = recent_hit - prior_hit
        if abs(hit_delta) >= .12:
            hit_cards.append(_card(
                market="Batter hits", icon="⚾️", player_id=str(pid), name=name, team=team,
                headline=(f"A hit in {int((recent['hits'] >= 1).sum())} of his last 10 games"),
                detail=(f"{_pct(recent_hit)} recently vs {_pct(prior_hit)} beforehand"),
                tone="up" if hit_delta > 0 else "down", value=abs(hit_delta)))

        recent_k2 = float((recent["strikeouts"] >= 2).mean())
        prior_k2 = float((prior["strikeouts"] >= 2).mean())
        k_delta = recent_k2 - prior_k2
        if abs(k_delta) >= .12:
            if k_delta < 0:
                headline = f"2+ strikeouts in only {int((recent['strikeouts'] >= 2).sum())} of his last 10"
                tone = "up"
            else:
                headline = f"2+ strikeouts in {int((recent['strikeouts'] >= 2).sum())} of his last 10"
                tone = "down"
            k_cards.append(_card(
                market="Batter strikeouts", icon="⚾️", player_id=str(pid), name=name,
                team=team, headline=headline,
                detail=(f"{_pct(recent_k2)} recently vs {_pct(prior_k2)} beforehand"),
                tone=tone, value=abs(k_delta)))
    return {"streaks": sorted(streak_cards, key=lambda c: c["value"], reverse=True)[:4],
            "hits": sorted(hit_cards, key=lambda c: c["value"], reverse=True)[:6],
            "batter_k": sorted(k_cards, key=lambda c: c["value"], reverse=True)[:6]}


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
        cards.append(_card(
            market="Pitcher strikeouts", icon="⚾️", player_id=str(pid), name=name,
            team=team, headline=f"{recent_avg:.1f} strikeouts per start over his last 5",
            detail=f"Up from {prior_avg:.1f} in the previous {len(prior)} starts" if delta > 0
                   else f"Down from {prior_avg:.1f} in the previous {len(prior)} starts",
            tone="up" if delta > 0 else "down", value=abs(delta)))
    return sorted(cards, key=lambda c: c["value"], reverse=True)[:6]


def build_context(as_of: date | None = None, db_path: Path = DB_PATH) -> dict:
    today = as_of or date.today()
    # load_plate_appearances is exclusive; tomorrow includes every completed row through
    # the selected day while retaining the project's leakage-safe date boundary.
    pa = load_plate_appearances(as_of=today + timedelta(days=1), db_path=db_path)
    batter = _batter_cards(pa)
    sections = [
        {"slug": "streaks", "title": "Active hit streaks", "read": "The longest live streaks among players who appeared in the last 10 days.", "cards": batter["streaks"], "comparison": "Consecutive games"},
        {"slug": "hits", "title": "Batter hits", "read": "Who is reaching the hit column more—or less—often than before.", "cards": batter["hits"]},
        {"slug": "batter-k", "title": "Batter strikeouts", "read": "Where multi-strikeout games have changed most sharply.", "cards": batter["batter_k"]},
        {"slug": "pitcher-k", "title": "Pitcher strikeouts", "read": "Recent strikeout pace per start compared with the prior turn through the rotation.", "cards": _pitcher_cards(pa)},
    ]
    through = pa["game_date"].max().date() if not pa.empty else None
    return {"section": "trending", "league": "MLB", "sections": sections,
            "through": through, "has_data": any(s["cards"] for s in sections)}
