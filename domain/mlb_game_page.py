"""Immutable page-level domain models for the MLB game page (Phase 1).

These are league-specific view models assembled by services/mlb_game_page.py from
data strictly before the slate date (`as_of`). They reuse the shared `Opportunity`
and `DataStatus` models rather than duplicating them. Every field must be
traceable to a real calculation — no fabricated statistics.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.models import DataStatus, Opportunity


@dataclass(frozen=True)
class MLBIdentityMetric:
    """One offensive-identity dimension for a team (e.g. Power, Contact)."""

    name: str
    raw_value: float
    display_value: str
    league_rank: int | None          # 1 = best in the league sample
    percentile: float | None         # 0-100; None when sample is insufficient
    trend_direction: str | None      # "up" | "down" | "steady" | None
    evidence_text: str
    sample_note: str | None = None


@dataclass(frozen=True)
class MLBTeamIdentity:
    team: str
    logo_url: str | None
    recent_form_label: str           # "Trending Up" | "Trending Down" | "Holding Steady"
    recent_form_evidence: str
    metrics: tuple[MLBIdentityMetric, ...]
    identity_summary: str
    strengths: tuple[str, ...]
    vulnerabilities: tuple[str, ...]
    sample_context: str


@dataclass(frozen=True)
class MLBGameHero:
    away_team: str
    home_team: str
    away_logo_url: str | None
    home_logo_url: str | None
    scheduled_time: str
    venue: str | None
    game_status: str | None
    probable_away_pitcher: str | None
    probable_home_pitcher: str | None
    probable_pitcher_status: str     # "available" | "partial" | "unavailable"
    league_context: str              # "MLB" (division/standings not available in Phase 1)
    # Presentation-only summary fields (V1.1). Populated from already-computed
    # analytics — no new calculations.
    away_form_label: str | None = None      # "Trending Up" | "Trending Down" | "Holding Steady"
    away_form_dir: str | None = None        # "up" | "down" | "steady"
    home_form_label: str | None = None
    home_form_dir: str | None = None
    away_pitcher_k_pct: float | None = None
    away_pitcher_hand: str | None = None
    home_pitcher_k_pct: float | None = None
    home_pitcher_hand: str | None = None
    # Plain-English summaries (derived from the same analytics) for the hero.
    away_form_note: str | None = None
    home_form_note: str | None = None
    away_pitcher_note: str | None = None
    home_pitcher_note: str | None = None


@dataclass(frozen=True)
class MLBPlayerTrend:
    player_id: str
    player_name: str
    team: str
    headshot_url: str | None
    direction: str                   # "up" | "down"
    trend_score: float
    recent_window: str
    baseline_window: str
    recent_summary: str
    baseline_summary: str
    explanation: str
    sample_size: int


@dataclass(frozen=True)
class MLBKeyMatchup:
    title: str
    advantage: str                   # team name or "Even"
    confidence: str                  # "High" | "Moderate" | "Low"
    explanation: str
    supporting_metrics: tuple[str, ...]
    availability_note: str | None = None


@dataclass(frozen=True)
class MLBGameShape:
    label: str
    confidence: str                  # "High" | "Moderate" | "Low"
    early_edge: str | None
    offensive_driver: str
    volatility: str
    likely_shape: str
    supporting_facts: tuple[str, ...]
    narrative: tuple[str, ...] = ()   # plain-English read (presentation)


@dataclass(frozen=True)
class MLBStoryline:
    title: str
    explanation: str
    supporting_facts: tuple[str, ...]
    priority: float


@dataclass(frozen=True)
class MLBBatterTrend:
    """A confidence-building recent-form card for a batter (enriched trend)."""
    player_id: str
    name: str
    team: str
    headshot_url: str | None
    category: str                    # "Heating up" | "Cooling off" | "High conviction"
    tone: str                        # "up" | "down" | "neutral"
    dots: tuple[int, ...]            # per-game 1+ hit (1/0), oldest → newest
    windows: tuple[tuple[str, str], ...]   # ("L5", "4 / 5"), ("L10", "8 / 10"), …
    hit_streak: int
    line: str                        # e.g. "1+ Hit · Score 92"
    support: tuple[str, ...]
    risks: tuple[str, ...]


@dataclass(frozen=True)
class MLBPitcherTrend:
    """Per-start trend card for a probable starting pitcher."""
    pitcher_id: str
    name: str
    team: str
    headshot_url: str | None
    k_spark: tuple[int, ...]         # K's per start, oldest → newest
    hits_spark: tuple[int, ...]      # hits allowed per start, oldest → newest
    k_avg: float
    hits_avg: float
    k_pct: float | None              # season strikeout rate (per PA)
    k_dir: str                       # "up" | "down" | "steady"
    hits_dir: str
    starts: int
    props: tuple[str, ...]           # served SP props, e.g. "7+ K — 4 of last 5"
    caveat: str


@dataclass(frozen=True)
class MLBGamePage:
    hero: MLBGameHero
    game_story: tuple[str, ...]
    away_identity: MLBTeamIdentity
    home_identity: MLBTeamIdentity
    key_matchups: tuple[MLBKeyMatchup, ...]
    heating_up: tuple[MLBPlayerTrend, ...]
    cooling_off: tuple[MLBPlayerTrend, ...]
    opportunities: tuple[Opportunity, ...]
    game_shape: MLBGameShape | None
    storylines: tuple[MLBStoryline, ...]
    data_status: DataStatus
    generated_at: str
    as_of: str
    # Trend spotlights (added later): per-start SP trends + enriched batter trends
    # (heating/cooling + our ≥90 high-conviction picks).
    pitcher_trends: tuple[MLBPitcherTrend, ...] = ()
    batter_trends: tuple[MLBBatterTrend, ...] = ()
