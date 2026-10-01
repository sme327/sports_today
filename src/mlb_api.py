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
                # Bracket fields. A postseason schedule is published before most of its
                # participants are known: an unfilled slot is a *placeholder* team
                # ("HOU/CWS", "AL Higher Seed") with a real-looking id, so it has to be
                # flagged or it would be drawn as a club. "If necessary" games and a
                # time the league has not set yet are likewise the source's own facts.
                "official_date": game.get("officialDate"),
                "if_necessary": str(game.get("ifNecessary") or "N").upper() == "Y",
                "start_time_tbd": bool(status.get("startTimeTBD")),
                "away_placeholder": bool(away_side.get("team", {}).get("placeholder")),
                "home_placeholder": bool(home_side.get("team", {}).get("placeholder")),
                # e.g. "ALDS 'B' Game 1" — the only place the source names *which* series
                # of a round this is.
                "game_description": game.get("description"),
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


def schedule_range(start_date: date | str, end_date: date | str) -> list[dict]:
    """One StatsAPI request for a range of MLB games.

    The playoff page needs a forward-looking schedule, but making one request per day
    would turn a static export into dozens of network calls. StatsAPI accepts a bounded
    range, so the whole two-week watch list arrives atomically and uses the exact same
    parser as the daily slate.
    """
    start = start_date.isoformat() if hasattr(start_date, "isoformat") else str(start_date)
    end = end_date.isoformat() if hasattr(end_date, "isoformat") else str(end_date)
    response = requests.get(
        f"{BASE}/schedule",
        params={"sportId": 1, "startDate": start, "endDate": end,
                "hydrate": "probablePitcher,team,venue,seriesStatus"},
        timeout=20,
    )
    response.raise_for_status()
    return _parse_schedule(response.json())


def postseason_series(season: int) -> list[dict]:
    """The whole postseason bracket for a season, one request, series by series.

    StatsAPI publishes every round up front — Wild Card through World Series — with
    placeholder teams in the slots nobody has reached yet, which is what makes the
    bracket drawable before it is decided. Games go through the same parser as the slate,
    so a bracket game and a slate game can never disagree about a score or a state.
    """
    response = requests.get(
        f"{BASE}/schedule/postseason/series",
        params={"season": season, "sportId": 1,
                "hydrate": "probablePitcher,team,venue,seriesStatus"},
        timeout=20,
    )
    response.raise_for_status()
    out = []
    for entry in response.json().get("series") or []:
        meta = entry.get("series") or {}
        games = _parse_schedule({"dates": [{"games": entry.get("games") or []}]})
        out.append({"series_id": meta.get("id"), "game_type": meta.get("gameType"),
                    "games": games})
    return out


def postseason_seeds(season: int) -> dict[str, int]:
    """``{team_id: seed}`` for the twelve clubs in the field, from the final standings.

    MLB seeds its three division winners 1-3 and its three Wild Cards 4-6. The source
    states both halves directly — the clinch indicator says which kind of place a club
    won, and each group's rank carries the official tiebreakers (``leagueRank`` among
    the champions, ``wildCardRank`` among the rest) — so nothing here compares records
    itself. Empty until the field is set: a Wild Card rank in mid-September is a race
    position, not a seed.

    Keyed on ``clinchIndicator`` and **not** ``divisionChamp``: in 2026 the source set
    ``divisionChamp`` on the Phillies, a Wild Card whose division the Braves won, which
    gave the NL four champions. The indicator (``z``/``y`` division, ``w`` Wild Card)
    was right, and ``x`` — in, but not yet which way — means the field is not set.
    """
    response = requests.get(
        f"{BASE}/standings",
        params={"leagueId": "103,104", "season": season,
                "standingsTypes": "regularSeason"},
        timeout=20,
    )
    response.raise_for_status()
    return seeds_from_standings(response.json())


def seeds_from_standings(payload: dict) -> dict[str, int]:
    by_league: dict[int, list[dict]] = {}
    for record in payload.get("records") or []:
        league = (record.get("league") or {}).get("id")
        for team in record.get("teamRecords") or []:
            by_league.setdefault(league, []).append(team)

    seeds: dict[str, int] = {}
    for teams in by_league.values():
        # Only clubs that have *clinched* — a clinch indicator is the source saying the
        # place is theirs, not that they hold it today.
        marks = [str(t.get("clinchIndicator") or "").lower() for t in teams]
        if "x" in marks:
            continue                      # someone is in, but not yet which way
        champs = [t for t, m in zip(teams, marks) if m in ("y", "z")]
        wild = [t for t, m in zip(teams, marks) if m == "w"]
        if len(champs) != 3 or len(wild) != 3:
            continue                      # field not set yet — no seeds, not guesses

        def rank(t, key):
            try:
                return int(t.get(key))
            except (TypeError, ValueError):
                return 99
        champs.sort(key=lambda t: rank(t, "leagueRank"))
        wild.sort(key=lambda t: rank(t, "wildCardRank"))
        for seed, team in enumerate([*champs, *wild], 1):
            seeds[str((team.get("team") or {}).get("id"))] = seed
    return seeds


def head_to_head(season: int, team_id: int | str, opponent_id: int | str) -> dict[str, int]:
    """Regular-season wins by team id in one pairing: ``{"147": 7, "111": 6}``.

    Counted from decided games only. A game marked final with no winner (a suspended
    game resumed elsewhere, a tie called for weather) is not a win for anyone.
    """
    response = requests.get(
        f"{BASE}/schedule",
        params={"sportId": 1, "season": season, "gameType": "R",
                "teamId": team_id, "opponentId": opponent_id},
        timeout=20,
    )
    response.raise_for_status()
    wins = {str(team_id): 0, str(opponent_id): 0}
    for game in _parse_schedule(response.json()):
        if game["state"] != "final" or not game["winner"]:
            continue
        winner_id = str(game["away_id"] if game["winner"] == "away" else game["home_id"])
        if winner_id in wins:
            wins[winner_id] += 1
    return wins
