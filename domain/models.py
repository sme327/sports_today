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
    # Venue splits. A home-court claim is only worth making when the home side is
    # actually good at home — see editorial's upset rule.
    away_road_record: str | None = None
    home_home_record: str | None = None

    # Position within a multi-game series. Baseball plays the regular season in
    # series and every postseason is one, so this is context year-round, not just in
    # October. ``series_summary`` is the source's own wording for the state going
    # into the game ("Series tied 1-1", "TB leads 2-0") and is absent before the
    # opener, when there is nothing to report.
    series_game: int | None = None
    series_total: int | None = None
    # Which game of a doubleheader this is (1 or 2), from the source's own note. Without
    # it a slate lists the same matchup twice at different times and reads as a bug —
    # two "Matchup →" links to different pages with nothing to tell them apart.
    doubleheader_game: int | None = None
    series_summary: str | None = None
    # The leading side's tally and the trailing side's, not away/home — which team
    # leads is named in ``series_summary``. These two carry the shape of the series,
    # which is what the clinch/elimination arithmetic below needs.
    series_leader_wins: int | None = None
    series_trailing_wins: int | None = None

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
        if ordinary_week and not self.competition:
            # In the regular season the week is the whole story; "Regular Season ·
            # Wk 1" spends words to say what the reader already assumes.
            base = f"Week {self.week}"
            if self.neutral_site:
                base = f"{base} · Neutral site"
        else:
            base = self.context_label if notable else None

        # The doubleheader marker leads: it is what disambiguates two otherwise
        # identical cards, so it has to be the first thing read.
        dh = f"Game {self.doubleheader_game}" if self.doubleheader_game else None
        parts = [p for p in (dh, base, self.series_note) if p]
        return " · ".join(parts) or None

    @property
    def series_label(self) -> str | None:
        """"Game 3 of 7", or None outside a real multi-game series."""
        if self.series_game and self.series_total and self.series_total > 1:
            return f"Game {self.series_game} of {self.series_total}"
        return None

    @property
    def series_wins_needed(self) -> int | None:
        """Wins required to take the series — ``N // 2 + 1`` of a best-of-N."""
        if not self.series_total or self.series_total < 2:
            return None
        return self.series_total // 2 + 1

    @property
    def series_is_decided(self) -> bool:
        """True once one side has clinched, so the remaining games are dead rubber
        (regular season) or simply not played (postseason)."""
        needed = self.series_wins_needed
        return bool(needed and (self.series_leader_wins or 0) >= needed)

    @property
    def series_stakes(self) -> str | None:
        """What is on the line in *this* game of the series, or None.

        Derived purely from the series shape — no bracket, no standings. A leader one
        win short can clinch, which means the trailing side is playing to survive; a
        best-of-N tied at N-1 apiece is a decider. Silent when nothing hangs on the
        game, and silent once the series is already decided, because "faces
        elimination" would be false there.
        """
        needed, leader = self.series_wins_needed, (self.series_leader_wins or 0)
        trailing = self.series_trailing_wins or 0
        if not needed or self.series_is_decided or self.series_game is None:
            return None
        if leader == needed - 1 and trailing == needed - 1:
            return "Winner takes the series"
        if leader == needed - 1:
            # One side can finish it; the other is playing to stay alive. In a
            # postseason series that is elimination, in a three-game set it is not.
            return ("Elimination game" if self.is_postseason
                    else "Series on the line")
        return None

    @property
    def series_note(self) -> str | None:
        """The series detail worth showing, or None.

        Which detail depends on the stakes. In a postseason series the game number is
        the story — "Game 6 of 7" carries the tension by itself. In the regular season
        the position is dull ("Game 2 of 3" is most of baseball) while the standing
        within it is not, so the source's summary is used instead. Before the opener
        there is no state either way, so nothing is shown.
        """
        # What is at stake outranks where we are: "Elimination game" tells the reader
        # more than "Game 6 of 7", and a decider more than "Series tied 1-1".
        if self.series_stakes:
            return self.series_stakes
        if self.is_postseason:
            return self.series_label
        if self.series_summary and (self.series_game or 0) >= 2:
            # The source's wording is "TB leads 2-0" / "WSH wins 3-0", which sits a
            # few centimetres from the game's own score on a card and reads exactly
            # like one. Name it unless the phrasing already does ("Series tied 1-1").
            summary = self.series_summary
            return summary if "series" in summary.lower() else f"Series · {summary}"
        return None

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
    # The actual recent results this prop was scored from, **oldest first** so the row
    # reads left-to-right as time. A score compresses ten games into one number and hides
    # the shape — "4, 4, 4, 7, 4, 3, 9" and "7, 7, 11, 4, 4" can score alike while telling
    # very different stories. Evidence lines are our judgement; this is the fact under it,
    # and it lets a reader disagree with us.
    recent_line: list[float] = field(default_factory=list)
    # The bar each value is judged against, so the renderer can mark which games cleared.
    line_threshold: float | None = None
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

    @property
    def line_cleared(self) -> list[bool]:
        """Which recent games cleared the bar, respecting the prop's direction.

        An **under** clears at or below the bar, so testing ``>=`` would mark exactly the
        wrong games — a pitcher's best starts would render as failures. Empty when there
        is no bar to judge against.
        """
        if self.line_threshold is None:
            return []
        if (self.direction or "over") == "under":
            return [v <= self.line_threshold for v in self.recent_line]
        return [v >= self.line_threshold for v in self.recent_line]
