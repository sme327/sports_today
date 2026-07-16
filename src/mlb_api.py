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


def _score(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _state(abstract_game_state: str | None) -> str:
    """Normalize MLB abstractGameState to pre / live / final."""
    return {"Preview": "pre", "Live": "live", "Final": "final"}.get(abstract_game_state, "pre")


def _parse_schedule(payload: dict) -> list[dict]:
    games = []
    for day in payload.get("dates", []):
        for game in day.get("games", []):
            away_side = game.get("teams", {}).get("away", {})
            home_side = game.get("teams", {}).get("home", {})
            away = _team_fields(away_side.get("team", {}))
            home = _team_fields(home_side.get("team", {}))
            status = game.get("status", {})
            winner = ("away" if away_side.get("isWinner")
                      else "home" if home_side.get("isWinner") else None)
            games.append({
                "game_pk": game.get("gamePk"),
                "game_date": game.get("gameDate"),
                "status": status.get("detailedState"),
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
                "away_pitcher": away_side.get("probablePitcher", {}).get("fullName"),
                "home_pitcher": home_side.get("probablePitcher", {}).get("fullName"),
                "venue": game.get("venue", {}).get("name"),
                # Final-score V1 fields.
                "away_score": _score(away_side.get("score")),
                "home_score": _score(home_side.get("score")),
                "state": _state(status.get("abstractGameState")),
                "winner": winner,
                "status_detail": status.get("detailedState"),
            })
    return games


def schedule(game_date: date | str) -> list[dict]:
    d = game_date.isoformat() if hasattr(game_date, "isoformat") else str(game_date)
    response = requests.get(
        f"{BASE}/schedule",
        params={"sportId": 1, "date": d, "hydrate": "probablePitcher,team,venue"},
        timeout=20,
    )
    response.raise_for_status()
    return _parse_schedule(response.json())
