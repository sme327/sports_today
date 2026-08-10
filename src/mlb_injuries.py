"""Player availability for MLB, from StatsAPI roster status.

MLB already has the confirmed-lineup overlay, which is definitive *once lineups are
posted* — but that is late in the day, and most of the time someone looks at the app
the lineups are hours away. Roster status fills that window.

Measured on one game before it started: **13 of 40 scored batters** were unavailable —
two on the 60-day injured list, four on shorter stints, six reassigned to the minors.
They are capped by the lineup overlay once lineups appear, but before that they score
normally, and every one of them is written into the snapshot ledger only to void.

Joined on the StatsAPI player id, which is the same id the plate-appearance feed
stores, so this is an exact match or nothing.
"""

from __future__ import annotations

import requests

from src.availability import InjuryReport, PlayerStatus

_ROSTER = "https://statsapi.mlb.com/api/v1/teams/{team_id}/roster"

# StatsAPI roster status is effectively binary: "A" (active) or some flavour of
# unavailable. There is no questionable tier here — a day-to-day player stays active
# on the roster — so everything non-active is treated as out and nothing is guessed.
_ACTIVE = "A"


def parse(payload: dict) -> InjuryReport:
    """Normalize one team's roster payload into an InjuryReport."""
    out: dict[str, PlayerStatus] = {}
    for entry in payload.get("roster") or []:
        person = entry.get("person") or {}
        pid = str(person.get("id") or "")
        status = entry.get("status") or {}
        code = str(status.get("code") or "")
        if not pid or not code or code == _ACTIVE:
            continue
        description = str(status.get("description") or "Unavailable")
        out[pid] = PlayerStatus(
            athlete_id=pid,
            name=str(person.get("fullName") or ""),
            status="Out",                 # normalized tier
            detail=description,           # StatsAPI's own wording, e.g. "Injured 10-Day"
        )
    return InjuryReport(out=out)


def fetch_teams(team_ids, timeout: int = 20) -> InjuryReport:
    """Merged availability for several teams. Empty on any failure, and an empty
    report is explicitly not a statement that everyone is fit."""
    merged: dict[str, PlayerStatus] = {}
    for team_id in team_ids:
        if not team_id:
            continue
        try:
            response = requests.get(_ROSTER.format(team_id=team_id),
                                    params={"rosterType": "fullRoster"}, timeout=timeout)
            response.raise_for_status()
            merged.update(parse(response.json()).out)
        except Exception:
            continue                      # one bad team must not blank the rest
    return InjuryReport(out=merged)
