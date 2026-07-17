"""Immutable page-level models for the MLS matchup page.

Soccer-designed (not translated from baseball or basketball). The page answers
"what kind of match am I about to watch?" — so the models are tactical and
identity-first, with an explicit per-section :class:`DataState` so the layout is
stable while the underlying intelligence grows (rule-based → opponent-aware →
formation-aware). Reuses the shared :class:`DataStatus`.

Honesty is structural here: sections that need a soccer-stats pipeline that does
not exist yet carry ``DataState.UNAVAILABLE``/``PROJECTED`` and render their real
component shell with an honest explanation — never fabricated numbers or
team-specific tactical claims. Everything marked ``AVAILABLE`` is real provider
data (records, recent form, colors, logos) or generic, clearly-labeled guidance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from domain.models import DataStatus


class DataState(str, Enum):
    """How complete a section's data is, right now.

    The layout renders identically across states; only the intelligence and the
    badge change. ``AVAILABLE`` = real, trustworthy data. ``PARTIAL`` = some rows
    real, others awaiting collection. ``PROJECTED`` = a best-effort estimate,
    clearly labeled (e.g. a lineup before it is confirmed). ``UNAVAILABLE`` = the
    supporting pipeline is not built yet; shown honestly, never faked.
    """

    AVAILABLE = "available"
    PROJECTED = "projected"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"

    @property
    def badge(self) -> str:
        return {
            "available": "Live",
            "projected": "Projected",
            "partial": "Partial",
            "unavailable": "Coming soon",
        }[self.value]

    @property
    def tone(self) -> str:
        # Drives the badge color class (see .mls-badge in app.css).
        return {
            "available": "ok",
            "projected": "warn",
            "partial": "warn",
            "unavailable": "muted",
        }[self.value]


# --------------------------------------------------------------- HERO --------
@dataclass(frozen=True)
class MLSTeamLine:
    name: str
    short: str
    logo: str | None
    color: str | None            # brand accent (contrast-guarded at render time)
    record: str | None           # "W-D-L"
    form: tuple[str, ...]        # ("W","D","L",...) oldest → most recent
    points_display: str | None   # e.g. "18 pts" (W*3 + D), or None if unknown
    standing: str | None = None  # e.g. "6th in West · 24 pts" (real, from standings)


@dataclass(frozen=True)
class MLSHero:
    competition: str
    kickoff: str
    venue: str | None
    broadcast: str | None
    away: MLSTeamLine
    home: MLSTeamLine
    state: str | None            # "pre" | "live" | "final"
    away_score: int | None
    home_score: int | None
    status_detail: str | None


# ------------------------------------------------------- MATCHUP SNAPSHOT -----
@dataclass(frozen=True)
class MLSSnapshotRow:
    label: str
    away_value: str
    home_value: str
    better: str | None           # "away" | "home" | "even" | None (no data)
    state: DataState


@dataclass(frozen=True)
class MLSSnapshot:
    state: DataState
    rows: tuple[MLSSnapshotRow, ...]
    note: str


# ------------------------------------------------------- TACTICAL MATCHUP -----
@dataclass(frozen=True)
class MLSTacticalRow:
    dimension: str               # measured proxy: "Ball Share", "Shot Volume", ...
    lean: str | None             # "away" | "home" | "even" | None (awaiting)
    away_label: str              # away value display (e.g. "10.8")
    home_label: str              # home value display
    explanation: str             # exact evidence sentence
    state: DataState
    confidence: str = ""         # "Moderate" | "Low" (real-data rows)


@dataclass(frozen=True)
class MLSTactical:
    state: DataState
    rows: tuple[MLSTacticalRow, ...]
    note: str
    summary: str = ""            # compact "similar profile" message when rows is empty


# --------------------------------------------------------- KEY STORYLINES -----
@dataclass(frozen=True)
class MLSStoryline:
    title: str
    detail: str
    evidence: tuple[str, ...]
    confidence: str              # "High" | "Moderate" | "Low"
    tone: str                    # "up" | "down" | "neutral"


@dataclass(frozen=True)
class MLSStorylines:
    state: DataState
    items: tuple[MLSStoryline, ...]
    note: str


# -------------------------------------------------------- PROJECTED LINEUPS ---
@dataclass(frozen=True)
class MLSPitchSlot:
    role: str                    # "GK" | "DF" | "MF" | "FW"
    x: float                     # 0–100 across the pitch width
    y: float                     # 0–100 up the pitch (own goal 0 → attack 100)
    name: str | None             # None until lineups are collected


@dataclass(frozen=True)
class MLSLineup:
    team: str
    color: str | None
    formation: str | None        # e.g. "4-3-3", or None when unknown
    slots: tuple[MLSPitchSlot, ...]
    note: str


@dataclass(frozen=True)
class MLSLineups:
    state: DataState
    away: MLSLineup
    home: MLSLineup


# --------------------------------------------------------- PLAYERS TO WATCH ---
@dataclass(frozen=True)
class MLSArchetype:
    name: str                    # "Finisher", "Creator", ...
    description: str
    player: str | None           # None until squad data is collected


@dataclass(frozen=True)
class MLSPlayersToWatch:
    state: DataState
    archetypes: tuple[MLSArchetype, ...]
    note: str


# -------------------------------------------------------- ATTACKING PROFILE ---
@dataclass(frozen=True)
class MLSAttackDimension:
    label: str                   # measured: "Shot accuracy", "Crossing volume", ...
    away_value: str
    home_value: str
    state: DataState
    better: str | None = None    # "away" | "home" | "even" | None


@dataclass(frozen=True)
class MLSAttacking:
    state: DataState
    away_team: str
    home_team: str
    dimensions: tuple[MLSAttackDimension, ...]
    note: str
    summary: str = ""            # compact message when few rows survive suppression


# --------------------------------------------------------------- DISCIPLINE ---
@dataclass(frozen=True)
class MLSDisciplineRow:
    label: str
    away_value: str
    home_value: str
    state: DataState
    better: str | None = None    # "away" | "home" | "even" | None (lower fouls/cards = better)


@dataclass(frozen=True)
class MLSDiscipline:
    state: DataState
    rows: tuple[MLSDisciplineRow, ...]
    note: str
    summary: str = ""            # compact "similar profile" message when rows is empty


# ----------------------------------------------------- WHAT TO WATCH TIMELINE -
@dataclass(frozen=True)
class MLSTimelinePhase:
    marker: str                  # "Pregame", "0–15'", "Midfield", ...
    title: str
    guidance: str
    kind: str                    # "generic" | "data"


@dataclass(frozen=True)
class MLSTimeline:
    state: DataState
    phases: tuple[MLSTimelinePhase, ...]
    note: str


# ------------------------------------------------------------- HONEST GAPS ----
@dataclass(frozen=True)
class MLSHonestGap:
    label: str
    detail: str


@dataclass(frozen=True)
class MLSHonestGaps:
    items: tuple[MLSHonestGap, ...]


# ----------------------------------------------------------------- THE PAGE ---
@dataclass(frozen=True)
class MLSGamePage:
    hero: MLSHero
    snapshot: MLSSnapshot
    tactical: MLSTactical
    storylines: MLSStorylines
    lineups: MLSLineups
    players: MLSPlayersToWatch
    attacking: MLSAttacking
    discipline: MLSDiscipline
    timeline: MLSTimeline
    honest_gaps: MLSHonestGaps
    data_status: DataStatus
    generated_at: str
    as_of: str
