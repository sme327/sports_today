from __future__ import annotations

from datetime import date, datetime, timezone
import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"


FLAG_CODES = {
    "ARG": "ar",
    "ENG": "gb-eng",
    "ESP": "es",
    "FRA": "fr",
    "BEL": "be",
    "CAN": "ca",
    "MAR": "ma",
    "NOR": "no",
    "SUI": "ch",
    "COL": "co",
    "USA": "us",
    "MEX": "mx",
    "BRA": "br",
    "JPN": "jp",
    "GER": "de",
    "PAR": "py",
    "NED": "nl",
    "SWE": "se",
    "POR": "pt",
    "CRO": "hr",
    "EGY": "eg",
    "GHA": "gh",
    "RSA": "za",
    "AUS": "au",
    "ECU": "ec",
    "AUT": "at",
    "SEN": "sn",
    "BIH": "ba",
}


def country_flag(abbreviation: str | None) -> str | None:
    code = FLAG_CODES.get((abbreviation or "").upper())
    return f"https://flagcdn.com/w160/{code}.png" if code else None

# Reliable fallback for the remaining 2026 World Cup slate. The ESPN source is
# attempted first so participants/results can update automatically.
FALLBACK_GAMES = {
    "2026-07-15": [{
        "game_id": "wc-53452535",
        "game_date": "2026-07-15T19:00:00Z",
        "status": "Scheduled",
        "away": "England",
        "home": "Argentina",
        "away_short": "England",
        "home_short": "Argentina",
        "away_abbr": "ENG",
        "home_abbr": "ARG",
        "away_logo": country_flag("ENG"),
        "home_logo": country_flag("ARG"),
        "venue": "Mercedes-Benz Stadium",
        "round": "Semifinal",
        "broadcast": "FOX, Telemundo",
    }],
    "2026-07-18": [{
        "game_id": "wc-53452539",
        "game_date": "2026-07-18T21:00:00Z",
        "status": "Scheduled",
        "away": "France",
        "home": "Semifinal loser",
        "away_short": "France",
        "home_short": "TBD",
        "away_abbr": "FRA",
        "home_abbr": "TBD",
        "away_logo": country_flag("FRA"),
        "home_logo": None,
        "venue": "Hard Rock Stadium",
        "round": "Third-place match",
        "broadcast": "",
    }],
    "2026-07-19": [{
        "game_id": "wc-53452537",
        "game_date": "2026-07-19T19:00:00Z",
        "status": "Scheduled",
        "away": "Spain",
        "home": "Semifinal winner",
        "away_short": "Spain",
        "home_short": "TBD",
        "away_abbr": "ESP",
        "home_abbr": "TBD",
        "away_logo": country_flag("ESP"),
        "home_logo": None,
        "venue": "New York New Jersey Stadium",
        "round": "World Cup Final",
        "broadcast": "",
    }],
}


def _logo(team: dict) -> str | None:
    logos = team.get("logos") or []
    return logos[0].get("href") if logos else None


def _parse_espn(payload: dict) -> list[dict]:
    games: list[dict] = []
    for event in payload.get("events", []):
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})
        home_team = home.get("team", {})
        away_team = away.get("team", {})
        broadcasts: list[str] = []
        for item in competition.get("broadcasts") or []:
            broadcasts.extend(item.get("names") or [])
        round_name = (
            competition.get("type", {}).get("abbreviation")
            or event.get("season", {}).get("slug")
            or ""
        )
        games.append({
            "game_id": event.get("id"),
            "game_date": event.get("date"),
            "status": event.get("status", {}).get("type", {}).get("detail")
                or event.get("status", {}).get("type", {}).get("description"),
            "away": away_team.get("displayName"),
            "home": home_team.get("displayName"),
            "away_short": away_team.get("shortDisplayName")
                or away_team.get("name")
                or away_team.get("abbreviation"),
            "home_short": home_team.get("shortDisplayName")
                or home_team.get("name")
                or home_team.get("abbreviation"),
            "away_abbr": away_team.get("abbreviation"),
            "home_abbr": home_team.get("abbreviation"),
            "away_logo": _logo(away_team) or country_flag(away_team.get("abbreviation")),
            "home_logo": _logo(home_team) or country_flag(home_team.get("abbreviation")),
            "venue": competition.get("venue", {}).get("fullName"),
            "round": round_name,
            "broadcast": ", ".join(dict.fromkeys(broadcasts)),
        })
    return games


def schedule(game_date: date | str) -> list[dict]:
    date_key = game_date.isoformat() if hasattr(game_date, "isoformat") else str(game_date)
    token = date_key.replace("-", "")
    try:
        response = requests.get(BASE, params={"dates": token, "limit": 20}, timeout=15)
        response.raise_for_status()
        games = _parse_espn(response.json())
        if games:
            return games
    except Exception:
        pass
    return [dict(game) for game in FALLBACK_GAMES.get(date_key, [])]
