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

from dataclasses import dataclass, field

import requests

_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/{path}/summary"

# ESPN's status strings, normalized to what a reader needs to decide.
# OUT is disqualifying; QUESTIONABLE needs saying; everything else is noise.
_OUT = {"out", "suspended", "injured reserve", "not with team"}
_QUESTIONABLE = {"day-to-day", "questionable", "doubtful", "game-time decision"}


@dataclass(frozen=True)
class PlayerStatus:
    athlete_id: str
    name: str
    status: str          # ESPN's own wording, e.g. "Day-To-Day"
    detail: str          # e.g. "Neck", "Coach's Decision"
    return_date: str | None = None

    @property
    def is_out(self) -> bool:
        return self.status.strip().lower() in _OUT

    @property
    def is_questionable(self) -> bool:
        return self.status.strip().lower() in _QUESTIONABLE

    @property
    def note(self) -> str:
        """One sentence for the evidence block."""
        reason = f" ({self.detail})" if self.detail else ""
        if self.is_out:
            return f"Listed OUT{reason} — not expected to play"
        return f"Listed {self.status}{reason} — availability unconfirmed"


@dataclass(frozen=True)
class InjuryReport:
    out: dict[str, PlayerStatus] = field(default_factory=dict)
    questionable: dict[str, PlayerStatus] = field(default_factory=dict)

    def status_for(self, athlete_id: object) -> PlayerStatus | None:
        key = str(athlete_id or "")
        return self.out.get(key) or self.questionable.get(key)

    @property
    def known(self) -> bool:
        """False when the source told us nothing — the caller must then stay silent
        rather than treat an empty report as a clean bill of health."""
        return bool(self.out or self.questionable)


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
