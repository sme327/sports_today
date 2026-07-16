"""Immutable page-level models for the WNBA matchup page.

Assembled by services/wnba_game_page.py from player game logs strictly before the
slate date. Basketball-designed (not translated from baseball). Reuses shared
`Opportunity` and `DataStatus`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.models import DataStatus, Opportunity


@dataclass(frozen=True)
class WNBAMetric:
    name: str
    display_value: str
    percentile: float | None
    league_rank: int | None
    evidence_text: str


@dataclass(frozen=True)
class WNBASnapshot:
    label: str
    value: str
    sub: str | None = None


@dataclass(frozen=True)
class WNBAFeatured:
    player_id: str
    name: str
    headshot: str | None
    line: str


@dataclass(frozen=True)
class WNBAHero:
    away_team: str
    home_team: str
    away_logo: str | None
    home_logo: str | None
    away_record: str
    home_record: str
    tip_time: str
    venue: str | None
    away_featured: WNBAFeatured | None
    home_featured: WNBAFeatured | None
    series: str | None
    state: str | None
    away_score: int | None
    home_score: int | None
    status_detail: str | None


@dataclass(frozen=True)
class WNBATeamIdentity:
    team: str
    logo: str | None
    record: str
    labels: tuple[str, ...]
    summary: str
    metrics: tuple[WNBAMetric, ...]
    strengths: tuple[str, ...]
    vulnerabilities: tuple[str, ...]
    sample_context: str
    form_results: tuple[str, ...]   # ("W","L",...) last 5
    streak: str


@dataclass(frozen=True)
class WNBABattlefield:
    title: str
    explanation: str
    advantage: str                  # team name or "Even"
    confidence: str                 # "High" | "Moderate" | "Low"
    supporting_metrics: tuple[str, ...]


@dataclass(frozen=True)
class WNBAShapePlayer:
    player_id: str
    name: str
    team: str
    headshot: str | None
    position: str | None
    role: str
    season_line: str
    trend: str
    strengths: str
    why_tonight: str


@dataclass(frozen=True)
class WNBAPlayerTrend:
    player_id: str
    name: str
    team: str
    headshot: str | None
    position: str | None
    direction: str                  # "up" | "down"
    category: str                   # "Trending Up" | "Potential Breakout" | ...
    recent_summary: str
    baseline_summary: str
    explanation: str


@dataclass(frozen=True)
class WNBASpark:
    label: str
    values: tuple[float, ...]
    display: str                    # latest value formatted


@dataclass(frozen=True)
class WNBATeamTrends:
    team: str
    logo: str | None
    sparks: tuple[WNBASpark, ...]


@dataclass(frozen=True)
class WNBAGamePage:
    hero: WNBAHero
    game_script: tuple[str, ...]
    away_snapshot: tuple[WNBASnapshot, ...]
    home_snapshot: tuple[WNBASnapshot, ...]
    away_identity: WNBATeamIdentity
    home_identity: WNBATeamIdentity
    battlefields: tuple[WNBABattlefield, ...]
    shape_players: tuple[WNBAShapePlayer, ...]
    trending_up: tuple[WNBAPlayerTrend, ...]
    trending_down: tuple[WNBAPlayerTrend, ...]
    away_trends: WNBATeamTrends | None
    home_trends: WNBATeamTrends | None
    opportunities: tuple[Opportunity, ...]
    data_status: DataStatus
    generated_at: str
    as_of: str
