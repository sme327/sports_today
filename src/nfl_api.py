"""NFL schedule via ESPN's public scoreboard (same shape as the soccer feed).

Schedule-only: Sports Today surfaces NFL games (preseason included) so the day's
slate is complete, but connects no player analysis or matchup deep-dive. Leakage
rules don't apply here — there is no scoring, only the schedule.
"""

from __future__ import annotations

from datetime import date

import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

_TYPE_LABEL = {1: "Preseason", 2: "Regular Season", 3: "Postseason"}


def _logo(team: dict) -> str | None:
    logos = team.get("logos") or []
    if logos:
        return logos[0].get("href")
    return team.get("logo")


def _score(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _state(status: dict) -> str:
    return {"pre": "pre", "in": "live", "post": "final"}.get(
        status.get("type", {}).get("state"), "pre")


def _winner(competitors: list[dict]) -> str | None:
    for c in competitors:
        if c.get("winner"):
            return c.get("homeAway")
    return None


def _round_label(event: dict) -> str:
    """A human round label, e.g. 'Preseason · Wk 2'. Preseason is the point here."""
    season = event.get("season") or {}
    slug = str(season.get("slug") or "").lower()
    if "pre" in slug:
        label = "Preseason"
    elif "post" in slug:
        label = "Postseason"
    elif "regular" in slug:
        label = "Regular Season"
    else:
        label = _TYPE_LABEL.get(season.get("type"), "NFL")
    week = (event.get("week") or {}).get("number")
    if week and label != "NFL":
        label = f"{label} · Wk {week}"
    return label


def _parse_nfl(payload: dict) -> list[dict]:
    games: list[dict] = []
    for event in payload.get("events", []):
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})
        home_team = home.get("team", {})
        away_team = away.get("team", {})
        status = event.get("status", {})
        stype = status.get("type", {})
        broadcasts: list[str] = []
        for item in competition.get("broadcasts") or []:
            broadcasts.extend(item.get("names") or [])
        games.append({
            "game_id": event.get("id"),
            "game_date": event.get("date"),
            "status": stype.get("detail") or stype.get("description"),
            "away": away_team.get("displayName"),
            "home": home_team.get("displayName"),
            "away_short": away_team.get("shortDisplayName") or away_team.get("name"),
            "home_short": home_team.get("shortDisplayName") or home_team.get("name"),
            "away_abbr": away_team.get("abbreviation"),
            "home_abbr": home_team.get("abbreviation"),
            "away_logo": _logo(away_team),
            "home_logo": _logo(home_team),
            "venue": competition.get("venue", {}).get("fullName"),
            "round": _round_label(event),
            "broadcast": ", ".join(dict.fromkeys(broadcasts)),
            "away_score": _score(away.get("score")),
            "home_score": _score(home.get("score")),
            "state": _state(status),
            "winner": _winner(competitors),
            "status_detail": stype.get("shortDetail") or stype.get("detail"),
        })
    return games


def schedule(game_date: date | str) -> list[dict]:
    """NFL games for a date (empty list on failure or a bye/off day)."""
    date_key = game_date.isoformat() if hasattr(game_date, "isoformat") else str(game_date)
    token = date_key.replace("-", "")
    try:
        response = requests.get(BASE, params={"dates": token, "limit": 40}, timeout=15)
        response.raise_for_status()
        return _parse_nfl(response.json())
    except Exception:
        return []
