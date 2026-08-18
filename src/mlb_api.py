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


# StatsAPI gameType → our normalized phase. Postseason rounds (Wild Card, Division,
# League Championship, World Series, generic Playoff) all collapse to "postseason";
# the specific round is carried separately by seriesDescription. Unknown/All-Star and
# exhibition codes map to None rather than being forced into a phase.
_GAME_TYPE_PHASE = {
    "S": "preseason", "R": "regular",
    "F": "postseason", "D": "postseason", "L": "postseason",
    "W": "postseason", "P": "postseason",
}


def _phase(game_type: object) -> str | None:
    return _GAME_TYPE_PHASE.get(str(game_type or "").upper().strip())


def _doubleheader_game(game: dict) -> int | None:
    """Which game of a doubleheader this is, or ``None`` for an ordinary fixture.

    Gated on ``doubleHeader`` rather than reading ``gameNumber`` alone: StatsAPI sets
    that field on *every* game, so trusting it directly would stamp "Game 1" on the whole
    slate. ``"S"`` is a split doubleheader (separate admissions) and ``"Y"`` a traditional
    one; ``"N"`` is the ordinary case.
    """
    if str(game.get("doubleHeader") or "N").upper() not in ("S", "Y"):
        return None
    number = game.get("gameNumber")
    return int(number) if str(number).isdigit() else None


def _record(side: dict) -> str | None:
    """"W-L" (or "W-L-T") from StatsAPI's structured leagueRecord. None when the
    block is absent — a team with no games yet must not read as 0-0."""
    rec = side.get("leagueRecord") or {}
    wins, losses = rec.get("wins"), rec.get("losses")
    if wins is None or losses is None:
        return None
    ties = rec.get("ties") or 0
    return f"{wins}-{losses}-{ties}" if ties else f"{wins}-{losses}"


def _series(game: dict) -> dict:
    """Where this game sits in its series, from StatsAPI's ``seriesStatus``.

    Semantics matter and are the source's, not ours: for a scheduled or in-progress
    game the block describes the series **going into** it ("Series tied 1-1"), and
    for a completed one the finished result ("WSH wins 3-0"). That is exactly the
    pregame framing we want, and it means no result is leaked into a preview.

    A one-game "series" carries no state worth showing, so it yields nothing.
    """
    status = game.get("seriesStatus") or {}
    total = status.get("totalGames") or game.get("gamesInSeries")
    number = status.get("gameNumber") or game.get("seriesGameNumber")
    if not total or total < 2:
        return {"series_game": None, "series_total": None, "series_summary": None}
    # ``wins``/``losses`` are the *leading* side's tally, not home/away — for
    # "ATH wins 2-1" the away team holds the 2. Which team leads is named in the
    # result string; these two carry the shape of the series, which is what the
    # clinch/elimination arithmetic needs.
    wins, losses = status.get("wins"), status.get("losses")
    return {
        "series_game": int(number) if number else None,
        "series_total": int(total),
        # e.g. "Series tied 1-1", "TB leads 2-0", "WSH wins 3-0". Absent before the
        # opener, when there is genuinely nothing to report.
        "series_summary": status.get("result") or None,
        "series_leader_wins": int(wins) if wins is not None else None,
        "series_trailing_wins": int(losses) if losses is not None else None,
    }


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
                "season": int(game["season"]) if str(game.get("season", "")).isdigit() else None,
                "phase": _phase(game.get("gameType")),
                # e.g. "Regular Season", "World Series" — MLB's own round wording.
                "series_description": game.get("seriesDescription"),
                "doubleheader_game": _doubleheader_game(game),
                **_series(game),
                "away_record": _record(away_side),
                "home_record": _record(home_side),
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
        params={"sportId": 1, "date": d, "hydrate": "probablePitcher,team,venue,seriesStatus"},
        timeout=20,
    )
    response.raise_for_status()
    return _parse_schedule(response.json())
