"""Normalized, league-agnostic domain models.

Every league adapter converts its raw feed into these structures so that the
router, views, and components never need to know league-specific shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SourceStatus(str, Enum):
    """Provenance of a piece of slate/opportunity data.

    Ordering of degraded fallback (owner decision 3):
    ``LIVE`` -> ``CACHED`` -> ``FALLBACK``. ``EMPTY`` means the source responded
    successfully with zero games (a legitimate off day), which must NOT trigger a
    league-wide fallback. ``ERROR`` means the source could not be reached/parsed.
    """

    LIVE = "live"
    CACHED = "cached"
    FALLBACK = "fallback"
    EMPTY = "empty"
    ERROR = "error"


@dataclass(frozen=True)
class DataStatus:
    """Where a dataset came from and whether it is trustworthy right now."""

    source: str
    status: SourceStatus
    fetched_at: datetime | None = None
    detail: str | None = None

    @property
    def is_live(self) -> bool:
        return self.status is SourceStatus.LIVE

    @property
    def is_usable(self) -> bool:
        """True when we have real games to show (live or cached)."""
        return self.status in (SourceStatus.LIVE, SourceStatus.CACHED)

    @property
    def is_degraded(self) -> bool:
        return self.status in (SourceStatus.CACHED, SourceStatus.FALLBACK, SourceStatus.ERROR)


class OpportunityMode(str, Enum):
    """How an opportunity set was generated.

    ``SLATE`` opportunities are restricted to teams playing on the slate date.
    ``LEAGUE_WIDE`` opportunities are the explicit degraded fallback and must be
    labeled as such; they are never presented as today-specific (owner decision 3).
    """

    SLATE = "slate"
    LEAGUE_WIDE = "league_wide"


@dataclass(frozen=True)
class Evidence:
    """A single piece of supporting or negative evidence.

    Opportunities carry plain-string evidence lists for rendering; this structured
    form is available for callers that need polarity-aware handling.
    """

    text: str
    polarity: str  # "support" | "risk"


@dataclass
class SlateGame:
    """One game/match on a given slate date, normalized across leagues."""

    league: str
    game_id: str
    start_time: datetime | None = None
    status: str | None = None

    away_id: str | None = None
    home_id: str | None = None
    away_name: str | None = None
    home_name: str | None = None
    away_short: str | None = None
    home_short: str | None = None
    away_abbr: str | None = None
    home_abbr: str | None = None
    away_logo: str | None = None
    home_logo: str | None = None

    venue: str | None = None
    # League-specific extras (probable pitchers, broadcast, round, etc.).
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def away_display(self) -> str:
        return self.away_short or self.away_name or "TBD"

    @property
    def home_display(self) -> str:
        return self.home_short or self.home_name or "TBD"

    @property
    def team_ids(self) -> list[str]:
        return [t for t in (self.away_id, self.home_id) if t]

    @property
    def team_identifiers(self) -> list[str]:
        """All name-ish tokens either side might be matched by (ids, abbrs, names)."""
        candidates = (
            self.away_id, self.home_id,
            self.away_abbr, self.home_abbr,
            self.away_name, self.home_name,
            self.away_short, self.home_short,
        )
        return [str(c) for c in candidates if c]


@dataclass
class Opportunity:
    """A normalized player-market-threshold opportunity.

    Superset of the common model from the brief plus the context fields required
    to snapshot and later interpret a ranking (owner decision 1 / section 3.2).
    """

    league: str
    player_id: str
    player_name: str
    team_id: str | None
    team_name: str | None
    market: str
    threshold: float | int | None
    opportunity_score: int
    stability_score: int
    supporting_evidence: list[str] = field(default_factory=list)
    negative_evidence: list[str] = field(default_factory=list)
    image_url: str | None = None
    data_status: DataStatus | None = None

    # Context for snapshots / deep dives.
    game_id: str | None = None
    mode: OpportunityMode = OpportunityMode.SLATE
    components: dict[str, float] = field(default_factory=dict)

    @property
    def sort_key(self) -> tuple[int, int]:
        return (self.opportunity_score, self.stability_score)

    @property
    def primary_support(self) -> str:
        return self.supporting_evidence[0] if self.supporting_evidence else ""

    @property
    def primary_risk(self) -> str:
        return self.negative_evidence[0] if self.negative_evidence else ""
