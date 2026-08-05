"""Confirmed batting lineups from the MLB StatsAPI (the same free, official source
as the schedule). Lineups post roughly 2–4 hours before first pitch; before that a
team's players list is empty, which we surface honestly as "not yet posted" rather
than guessing.

Joins are by MLB player id, which equals the vendor feed's ``batter_id`` (verified
1:1), and team names match the feed exactly — so no name-based joining is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import requests

from src.mlb_api import BASE

# A lineup is "posted" once its batting order is filled (9 hitters).
_FULL_LINEUP = 9


@dataclass(frozen=True)
class Lineups:
    """Today's posted lineups. ``slot`` maps ``batter_id -> batting-order slot``
    (1–9); ``posted_teams`` is the set of team names whose lineup is out."""
    slot: dict[int, int]
    posted_teams: frozenset[str]

    def is_posted(self, team_name: str | None) -> bool:
        return team_name in self.posted_teams


EMPTY_LINEUPS = Lineups(slot={}, posted_teams=frozenset())


def fetch_lineups(slate_date: date | str) -> Lineups:
    """Fetch posted batting lineups for a date. Raises on network/HTTP error so
    callers can decide how to degrade (the app caches this and falls back to
    ``EMPTY_LINEUPS``)."""
    d = slate_date.isoformat() if hasattr(slate_date, "isoformat") else str(slate_date)
    resp = requests.get(
        f"{BASE}/schedule",
        params={"sportId": 1, "date": d, "hydrate": "lineups,team"},
        timeout=20,
    )
    resp.raise_for_status()
    return _parse(resp.json())


def _parse(payload: dict) -> Lineups:
    slot: dict[int, int] = {}
    posted: set[str] = set()
    for day in payload.get("dates", []):
        for game in day.get("games", []):
            teams = game.get("teams", {})
            lineups = game.get("lineups") or {}
            for side, key in (("away", "awayPlayers"), ("home", "homePlayers")):
                players = lineups.get(key) or []
                if len(players) < _FULL_LINEUP:
                    continue                      # not posted yet — leave it out
                name = teams.get(side, {}).get("team", {}).get("name")
                if name:
                    posted.add(name)
                for order, player in enumerate(players, start=1):
                    pid = player.get("id")
                    if pid is not None:
                        slot[int(pid)] = order
    return Lineups(slot=slot, posted_teams=frozenset(posted))
