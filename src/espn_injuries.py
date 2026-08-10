"""Injury / availability report for a single game, from the ESPN summary endpoint.

The gap this closes was found the hard way. On 2026-08-09 the app's highest-rated
WNBA play was Kiah Stokes 4+ rebounds — biggest cushion on the board, cleared in five
of five — and she was listed **Day-To-Day with a neck injury** in an endpoint we
already call for other things. Knowing a player's own scoring history is worthless if
you do not know whether she is playing.

Joined on the **athlete id**, never the name: ESPN supplies the same ids our box-score
collector already stores, so a player is matched exactly or not at all.

One request per game, so callers should cache. Any failure yields an empty report and
the caller says nothing rather than implying everyone is fit.
"""

from __future__ import annotations

import requests

from src.availability import InjuryReport, PlayerStatus

_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/{path}/summary"

def parse(payload: dict) -> InjuryReport:
    """Normalize an ESPN summary payload into an InjuryReport."""
    out: dict[str, PlayerStatus] = {}
    questionable: dict[str, PlayerStatus] = {}
    for team in payload.get("injuries") or []:
        for item in team.get("injuries") or []:
            athlete = item.get("athlete") or {}
            aid = str(athlete.get("id") or "")
            if not aid:
                continue                      # no id, no claim
            details = item.get("details") or {}
            status = PlayerStatus(
                athlete_id=aid,
                name=str(athlete.get("displayName") or ""),
                status=str(item.get("status") or ""),
                detail=str(details.get("type") or ""),
                return_date=details.get("returnDate"),
            )
            if status.is_out:
                out[aid] = status
            elif status.is_questionable:
                questionable[aid] = status
    return InjuryReport(out=out, questionable=questionable)


def fetch(sport_path: str, event_id: str | int, timeout: int = 15) -> InjuryReport:
    """Injury report for one game. Empty (and ``known`` False) on any failure."""
    try:
        response = requests.get(_SUMMARY.format(path=sport_path),
                                params={"event": str(event_id)}, timeout=timeout)
        response.raise_for_status()
        return parse(response.json())
    except Exception:
        return InjuryReport()
