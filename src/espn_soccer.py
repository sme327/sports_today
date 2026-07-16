"""Neutral ESPN soccer scoreboard client (competition-parameterized).

One parser for any ESPN soccer competition (MLS = ``usa.1``, and the same shape
serves other leagues). Returns normalized dicts the league adapters convert into
``SlateGame``. Everything here is real provider data: teams, club logos, W-D-L
records, recent form (last five results), brand colors, venue, kickoff, and
Final-score V1 fields. No statistics are invented.

Kept separate from ``src/world_cup_api`` on purpose: World Cup uses national
flags and a hardcoded bracket fallback; club competitions use club logos and have
no fallback. A future refactor may migrate World Cup onto this client.
"""

from __future__ import annotations

from datetime import date

import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"

# Known competition slugs (extend as leagues are added).
MLS = "usa.1"


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


def _record(competitor: dict) -> str | None:
    """The team's overall W-D-L summary, e.g. '5-5-5'."""
    for rec in competitor.get("records") or []:
        if rec.get("type") == "total" or rec.get("name") == "All Splits":
            return rec.get("summary")
    recs = competitor.get("records") or []
    return recs[0].get("summary") if recs else None


def _form(competitor: dict) -> tuple[str, ...]:
    """Recent results oldest→newest as a tuple like ('D','W','L','W','D')."""
    raw = competitor.get("form") or ""
    return tuple(ch for ch in str(raw).upper() if ch in ("W", "D", "L"))


def _color(team: dict) -> str | None:
    c = team.get("color")
    if not c:
        return None
    c = str(c).lstrip("#")
    return f"#{c}" if len(c) in (3, 6) else None


def _broadcast(competition: dict) -> str:
    names: list[str] = []
    for item in competition.get("broadcasts") or []:
        names.extend(item.get("names") or [])
    return ", ".join(dict.fromkeys(names))


def _competition_label(event: dict, slug: str) -> str:
    season = event.get("season") or {}
    slug_name = season.get("slug") or ""
    pretty = {
        "regular-season": "MLS Regular Season",
        "post-season": "MLS Cup Playoffs",
    }
    if slug == MLS:
        return pretty.get(slug_name, "Major League Soccer")
    return slug_name.replace("-", " ").title() or slug


def parse(payload: dict, slug: str) -> list[dict]:
    """Parse an ESPN soccer scoreboard payload into normalized game dicts."""
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
            "away_logo": away_team.get("logo"),
            "home_logo": home_team.get("logo"),
            "away_color": _color(away_team),
            "home_color": _color(home_team),
            "away_record": _record(away),
            "home_record": _record(home),
            "away_form": _form(away),
            "home_form": _form(home),
            "venue": (competition.get("venue") or {}).get("fullName"),
            "competition": _competition_label(event, slug),
            "broadcast": _broadcast(competition),
            # Final-score V1 fields.
            "away_score": _score(away.get("score")),
            "home_score": _score(home.get("score")),
            "state": _state(status),
            "winner": _winner(competitors),
            "status_detail": stype.get("shortDetail") or stype.get("detail"),
        })
    return games


def schedule(competition_slug: str, game_date: date | str) -> list[dict]:
    """Fetch and parse a competition's games for a date. [] on any failure."""
    date_key = game_date.isoformat() if hasattr(game_date, "isoformat") else str(game_date)
    token = date_key.replace("-", "")
    try:
        response = requests.get(
            BASE.format(slug=competition_slug),
            params={"dates": token, "limit": 30},
            timeout=15,
        )
        response.raise_for_status()
        return parse(response.json(), competition_slug)
    except Exception:
        return []
