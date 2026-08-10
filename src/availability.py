"""Whether a player is available tonight — source-agnostic vocabulary.

Every provider words this differently (ESPN says "Day-To-Day", MLB StatsAPI says
"Injured 10-Day" or "Reassigned to Minors"), so each source normalises into these
types and the scorers only ever see one shape.

The load-bearing distinction is between *known unavailable* and *nothing known*.
An empty report must never read as a clean bill of health — see ``known``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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




def out(status: PlayerStatus) -> bool:
    return status.is_out
