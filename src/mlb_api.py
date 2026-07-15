from __future__ import annotations

from datetime import date
import requests

BASE = "https://statsapi.mlb.com/api/v1"


def _team_fields(team: dict) -> dict:
    team_id = team.get("id")
    return {
        "name": team.get("name"),
        "short": team.get("teamName") or team.get("clubName") or team.get("abbreviation") or team.get("name"),
        "abbreviation": team.get("abbreviation"),
        "id": team_id,
        "logo": f"https://www.mlbstatic.com/team-logos/{team_id}.svg" if team_id else None,
    }


def schedule(game_date: date | str) -> list[dict]:
    d = game_date.isoformat() if hasattr(game_date, "isoformat") else str(game_date)
    response = requests.get(
        f"{BASE}/schedule",
        params={"sportId": 1, "date": d, "hydrate": "probablePitcher,team,venue"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    games = []
    for day in payload.get("dates", []):
        for game in day.get("games", []):
            away_raw = game.get("teams", {}).get("away", {}).get("team", {})
            home_raw = game.get("teams", {}).get("home", {}).get("team", {})
            away = _team_fields(away_raw)
            home = _team_fields(home_raw)
            games.append({
                "game_pk": game.get("gamePk"),
                "game_date": game.get("gameDate"),
                "status": game.get("status", {}).get("detailedState"),
                "away": away["name"],
                "home": home["name"],
                "away_short": away["short"],
                "home_short": home["short"],
                "away_abbr": away["abbreviation"],
                "home_abbr": home["abbreviation"],
                "away_id": away["id"],
                "home_id": home["id"],
                "away_logo": away["logo"],
                "home_logo": home["logo"],
                "away_pitcher": game.get("teams", {}).get("away", {}).get("probablePitcher", {}).get("fullName"),
                "home_pitcher": game.get("teams", {}).get("home", {}).get("probablePitcher", {}).get("fullName"),
                "venue": game.get("venue", {}).get("name"),
            })
    return games
