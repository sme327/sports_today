"""Shared ESPN scoreboard client for schedule-only leagues (NFL, NHL, NBA, NCAA FB…).

ESPN's public site API returns the same event shape across sports, so one fetch +
parse serves every schedule-only league; each adapter maps the normalized dicts to
``SlateGame`` and picks its own round-label style. Schedule-only: no player analysis,
so leakage rules don't apply (there's no scoring, only the schedule).
"""

from __future__ import annotations

from datetime import date

import requests

_BASE = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
_TYPE_LABEL = {1: "Preseason", 2: "Regular Season", 3: "Postseason", 4: "Postseason"}
# ESPN's numeric season type → our normalized phase vocabulary.
_PHASE_BY_TYPE = {1: "preseason", 2: "regular", 3: "postseason", 4: "postseason"}


def team_records(competitor: dict) -> dict[str, str]:
    """A competitor's record summaries keyed by ESPN's record type.

    Availability varies by league and is never assumed: NFL and college football
    supply them, the NHL scoreboard omits the block entirely. Absent → empty dict,
    and callers show nothing rather than a zero.
    """
    out: dict[str, str] = {}
    for rec in competitor.get("records") or []:
        summary, kind = rec.get("summary"), rec.get("type")
        if summary and kind:
            out[str(kind)] = str(summary)
    return out


def _int(value: object) -> int | None:
    """A clean int, or None — ESPN sends numbers as ints, strings, or not at all."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


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


def _rank(competitor: dict) -> int | None:
    """AP/coaches poll rank (NCAA), or None. ESPN uses 99/0 for unranked."""
    rank = (competitor.get("curatedRank") or {}).get("current")
    return int(rank) if isinstance(rank, (int, float)) and 0 < rank < 99 else None


def parse_events(payload: dict) -> list[dict]:
    """Normalize an ESPN scoreboard payload into league-agnostic game dicts."""
    games: list[dict] = []
    for event in payload.get("events", []):
        comp = (event.get("competitions") or [{}])[0]
        competitors = comp.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})
        ht, at = home.get("team", {}), away.get("team", {})
        status = event.get("status", {})
        stype = status.get("type", {})
        broadcasts: list[str] = []
        for item in comp.get("broadcasts") or []:
            broadcasts.extend(item.get("names") or [])
        season = event.get("season") or {}
        games.append({
            "game_id": event.get("id"),
            "game_date": event.get("date"),
            "status": stype.get("detail") or stype.get("description"),
            "away": at.get("displayName"),
            "home": ht.get("displayName"),
            "away_short": at.get("shortDisplayName") or at.get("name"),
            "home_short": ht.get("shortDisplayName") or ht.get("name"),
            "away_abbr": at.get("abbreviation"),
            "home_abbr": ht.get("abbreviation"),
            "away_logo": _logo(at),
            "home_logo": _logo(ht),
            "away_rank": _rank(away),
            "home_rank": _rank(home),
            "venue": (comp.get("venue") or {}).get("fullName"),
            "neutral_site": bool(comp.get("neutralSite")),
            "broadcast": ", ".join(dict.fromkeys(broadcasts)),
            "away_score": _score(away.get("score")),
            "home_score": _score(home.get("score")),
            "state": _state(status),
            "winner": _winner(competitors),
            "status_detail": stype.get("shortDetail") or stype.get("detail"),
            "season_type": season.get("type"),
            "season_slug": season.get("slug"),
            "season": _int(season.get("year")),
            "phase": season_phase(season.get("slug"), season.get("type")),
            "week": _int((event.get("week") or {}).get("number")),
            "away_record": team_records(away).get("total"),
            "home_record": team_records(home).get("total"),
            "away_home_away_record": team_records(away).get("awayrecord"),
            "home_home_away_record": team_records(home).get("homerecord"),
            "conference_game": bool(comp.get("conferenceCompetition")),
        })
    return games


def season_phase(slug: object, type_code: object) -> str | None:
    """Normalized season phase — ``preseason`` | ``regular`` | ``postseason``.

    The same vocabulary the ingested NFL feed uses (``nfl_team_games.season_type``), so
    a live game and a stored one can be compared without translating. Prefers ESPN's
    slug (more reliable) and falls back to its numeric type code. ``None`` when the
    source says nothing — never guessed.
    """
    text = str(slug or "").lower()
    if "pre" in text:
        return "preseason"
    if "post" in text:
        return "postseason"
    if "regular" in text:
        return "regular"
    return _PHASE_BY_TYPE.get(type_code)


def round_label(game: dict, *, with_week: bool = False) -> str:
    """A human round label from a parsed game, e.g. 'Preseason · Wk 2' or 'Regular
    Season'. ``with_week`` appends the week number (football/college)."""
    slug = str(game.get("season_slug") or "").lower()
    if "pre" in slug:
        base = "Preseason"
    elif "post" in slug:
        base = "Postseason"
    elif "regular" in slug:
        base = "Regular Season"
    else:
        base = _TYPE_LABEL.get(game.get("season_type"), "")
    week = game.get("week")
    if with_week and week:
        return f"{base} · Wk {week}" if base else f"Week {week}"
    return base


def fetch(sport_path: str, game_date: date | str, limit: int = 100) -> list[dict]:
    """Normalized games for a date (empty list on failure or an off day)."""
    key = game_date.isoformat() if hasattr(game_date, "isoformat") else str(game_date)
    token = key.replace("-", "")
    try:
        response = requests.get(_BASE.format(path=sport_path),
                                params={"dates": token, "limit": limit}, timeout=15)
        response.raise_for_status()
        return parse_events(response.json())
    except Exception:
        return []
