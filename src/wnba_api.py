from __future__ import annotations

from datetime import date
import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"

# ESPN occasionally omits logo arrays from scoreboard responses. These stable
# CDN fallbacks keep the slate visually complete.
WNBA_LOGO_CODES = {
    "ATL": "atl",
    "CHI": "chi",
    "CONN": "con",
    "CON": "con",
    "DAL": "dal",
    "GS": "gs",
    "GSV": "gs",
    "IND": "ind",
    "LA": "la",
    "LAS": "lv",
    "LV": "lv",
    "MIN": "min",
    "NY": "ny",
    "NYL": "ny",
    "PHX": "phx",
    "POR": "por",
    "SEA": "sea",
    "TOR": "tor",
    "WSH": "wsh",
}

WNBA_NAME_CODES = {
    "atlanta dream": "atl",
    "chicago sky": "chi",
    "connecticut sun": "con",
    "dallas wings": "dal",
    "golden state valkyries": "gs",
    "indiana fever": "ind",
    "las vegas aces": "lv",
    "los angeles sparks": "la",
    "minnesota lynx": "min",
    "new york liberty": "ny",
    "phoenix mercury": "phx",
    "portland fire": "por",
    "seattle storm": "sea",
    "toronto tempo": "tor",
    "washington mystics": "wsh",
}


def _logo(team: dict) -> str | None:
    logos = team.get("logos") or []
    if logos and logos[0].get("href"):
        return logos[0]["href"]

    abbreviation = str(team.get("abbreviation") or "").upper()
    display_name = str(team.get("displayName") or "").lower()
    code = WNBA_LOGO_CODES.get(abbreviation) or WNBA_NAME_CODES.get(display_name)
    if not code:
        return None
    return f"https://a.espncdn.com/i/teamlogos/wnba/500/{code}.png"


def schedule(game_date: date | str) -> list[dict]:
    if hasattr(game_date, "strftime"):
        date_token = game_date.strftime("%Y%m%d")
    else:
        date_token = str(game_date).replace("-", "")

    response = requests.get(BASE, params={"dates": date_token, "limit": 20}, timeout=20)
    response.raise_for_status()
    payload = response.json()

    games: list[dict] = []
    for event in payload.get("events", []):
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})
        home_team = home.get("team", {})
        away_team = away.get("team", {})

        broadcasts = []
        for item in competition.get("broadcasts") or []:
            broadcasts.extend(item.get("names") or [])

        games.append({
            "game_id": event.get("id"),
            "game_date": event.get("date"),
            "status": event.get("status", {}).get("type", {}).get("detail") or event.get("status", {}).get("type", {}).get("description"),
            "away": away_team.get("displayName"),
            "home": home_team.get("displayName"),
            "away_short": away_team.get("shortDisplayName") or away_team.get("name") or away_team.get("abbreviation"),
            "home_short": home_team.get("shortDisplayName") or home_team.get("name") or home_team.get("abbreviation"),
            "away_abbr": away_team.get("abbreviation"),
            "home_abbr": home_team.get("abbreviation"),
            "away_logo": _logo(away_team),
            "home_logo": _logo(home_team),
            "venue": competition.get("venue", {}).get("fullName"),
            "broadcast": ", ".join(dict.fromkeys(broadcasts)),
        })
    return games
