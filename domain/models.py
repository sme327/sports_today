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

    # Score/state (Final-score V1). Optional with safe defaults so older cached
    # SlateGame rows (serialized before these existed) still deserialize.
    away_score: int | None = None
    home_score: int | None = None
    state: str | None = None          # "pre" | "live" | "final" | None
    winner: str | None = None         # "away" | "home" | None
    status_detail: str | None = None  # e.g. "Final", "3rd Quarter", "AET"

    # Competition context — where this game sits in its competition. Every field is
    # optional and defaults to "unknown": a league that cannot supply one leaves it
    # None and the UI omits it, rather than showing a guess. All optional with safe
    # defaults so cached SlateGame rows written before these existed still deserialize.
    # NOTE: "season year" is whatever the source calls it, and the convention differs
    # by sport — ESPN labels the 2026-27 NHL/NBA season 2027 (end year), while the NFL
    # season starting Sept 2026 is 2026. We store the source's own value rather than
    # re-deriving one; compare seasons within a league, not across them.
    season: int | None = None          # the season year, e.g. 2026
    phase: str | None = None           # "preseason" | "regular" | "postseason"
    week: int | None = None            # week number, where the sport has weeks
    round_name: str | None = None      # human round/stage, e.g. "Preseason · Wk 2"
    competition: str | None = None     # tournament/competition when not league play
    neutral_site: bool = False
    conference_game: bool = False

    # Team standing going into this game — the raw material for editorial signals in
    # leagues that have no player props. Records are the source's own summary strings
    # ("8-3", "9-0-1"); rank is a poll/curated rank where the sport has one. Absent
    # for leagues that do not publish them (the NHL scoreboard omits records), which
    # is why every one is optional and unset means "not offered", never zero.
    away_record: str | None = None
    home_record: str | None = None
    away_rank: int | None = None
    home_rank: int | None = None

    # League-specific extras (probable pitchers, broadcast, etc.).
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def is_postseason(self) -> bool:
        return self.phase == "postseason"

    @property
    def notable_context(self) -> str | None:
        """The competition line, but only when it tells the reader something new.

        Most games are ordinary regular-season fixtures, so stamping "Regular Season"
        on every card would add noise and no information. This returns a label only
        when the context is genuinely worth knowing — a preseason or postseason game,
        a football week, a neutral site, or a named tournament round — and ``None``
        otherwise, so the card simply omits it.
        """
        ordinary_week = self.phase == "regular" and self.week is not None
        notable = (
            self.phase in ("preseason", "postseason")
            or self.week is not None
            or self.neutral_site
            or bool(self.round_name and self.phase != "regular")
        )
        if not notable:
            return None
        if ordinary_week and not self.competition:
            # In the regular season the week is the whole story; "Regular Season ·
            # Wk 1" spends words to say what the reader already assumes.
            label = f"Week {self.week}"
            return f"{label} · Neutral site" if self.neutral_site else label
        return self.context_label

    @property
    def context_label(self) -> str | None:
        """One short human line for the competition context, or None when the source
        gave us nothing. Prefers the explicit round label the league built."""
        if self.round_name:
            label = self.round_name
        elif self.week is not None:
            label = f"Week {self.week}"
        elif self.phase:
            label = {"preseason": "Preseason", "regular": "Regular Season",
                     "postseason": "Postseason"}[self.phase]
        else:
            label = self.competition or None
        # Prefix the competition only when it adds something. Sources overlap: MLS
        # reports competition "MLS Regular Season" while the phase renders "Regular
        # Season", and naively joining gives "MLS Regular Season · Regular Season".
        if label and self.competition:
            if self.competition in label:
                pass                                  # competition already stated
            elif label in self.competition:
                label = self.competition              # competition is the fuller form
            else:
                label = f"{self.competition} · {label}"
        if label and self.neutral_site:
            label = f"{label} · Neutral site"
        return label

    @property
    def has_score(self) -> bool:
        return self.away_score is not None and self.home_score is not None

    @property
    def is_final(self) -> bool:
        return self.state == "final"

    @property
    def is_live(self) -> bool:
        return self.state == "live"

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
    # Structured market identity (registry key + graded direction). Optional so
    # legacy callers still construct; the registry resolves text when absent.
    market_key: str | None = None
    direction: str | None = None
    supporting_evidence: list[str] = field(default_factory=list)
    negative_evidence: list[str] = field(default_factory=list)
    image_url: str | None = None
    # Optional secondary image (e.g. player headshot alongside a team logo).
    headshot_url: str | None = None
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
