"""Base class for schedule-only leagues fed by the ESPN scoreboard (NFL, NHL, NBA,
NCAA Football). Each concrete league is just a few class attributes; all the fetch →
SlateGame mapping lives here. Player analysis and deep-dives are intentionally absent
(``opportunities`` returns []); the game view renders the shared schedule-only page.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import pandas as pd

from domain.models import Opportunity, OpportunityMode, SlateGame
from src import espn_scoreboard


def _parse_start(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return pd.to_datetime(raw, utc=True).to_pydatetime()
    except Exception:
        return None


def _ranked(short: str | None, rank: int | None) -> str | None:
    """Prefix a poll rank onto a team's short name, e.g. '#5 Georgia'."""
    if short and rank:
        return f"#{rank} {short}"
    return short


class ScheduleOnlyESPN:
    """Mixin/base implementing the LeagueAdapter protocol for an ESPN-fed schedule."""

    supports_deep_dive = False
    chip_label = "Game"

    # Per-league configuration (set by subclasses):
    espn_path: str = ""          # e.g. "hockey/nhl"
    # ESPN caps a college scoreboard response at 25 events **per group**. Leagues split
    # across divisions must name their groups or they silently show a partial slate —
    # NCAAF was returning exactly 25 games on every busy Saturday. Single-league sports
    # (NFL/NBA/NHL) leave this empty. See src/espn_scoreboard.fetch.
    espn_groups: tuple[str | int, ...] = ()
    # ESPN truncates to `limit` *after* filtering. College basketball runs 169 games on a
    # busy night, so 100 silently drops the tail. Do not raise this globally: ESPN handles
    # very large values badly (limit=900 returned 19 games where limit=100 returned 45).
    espn_limit: int = 100
    with_week: bool = False      # append "· Wk N" (football/college)
    rank_prefix: bool = False    # prepend "#N " to ranked teams (NCAA)
    default_round: str = ""      # round label when the source omits one

    def describe_game(self, game: SlateGame) -> str:
        parts = [game.round_name or game.meta.get("round") or self.default_round]
        if game.venue:
            parts.append(game.venue)
        return " · ".join(p for p in parts if p)

    def fetch_schedule(self, slate_date: date) -> list[SlateGame]:
        games: list[SlateGame] = []
        for g in espn_scoreboard.fetch(self.espn_path, slate_date,
                                       limit=self.espn_limit,
                                       groups=self.espn_groups or None):
            away_short, home_short = g.get("away_short"), g.get("home_short")
            if self.rank_prefix:
                away_short = _ranked(away_short, g.get("away_rank"))
                home_short = _ranked(home_short, g.get("home_rank"))
            games.append(SlateGame(
                league=self.league,
                game_id=str(g.get("game_id")),
                start_time=_parse_start(g.get("game_date")),
                status=g.get("status"),
                away_name=g.get("away"),
                home_name=g.get("home"),
                away_short=away_short,
                home_short=home_short,
                away_abbr=g.get("away_abbr"),
                home_abbr=g.get("home_abbr"),
                away_logo=g.get("away_logo"),
                home_logo=g.get("home_logo"),
                venue=g.get("venue"),
                away_score=g.get("away_score"),
                home_score=g.get("home_score"),
                state=g.get("state"),
                winner=g.get("winner"),
                status_detail=g.get("status_detail"),
                season=g.get("season"),
                phase=g.get("phase"),
                week=g.get("week"),
                round_name=espn_scoreboard.round_label(g, with_week=self.with_week)
                           or self.default_round or None,
                neutral_site=bool(g.get("neutral_site")),
                doubleheader_game=g.get("doubleheader_game"),
                conference_game=bool(g.get("conference_game")),
                away_record=g.get("away_record"),
                home_record=g.get("home_record"),
                away_rank=g.get("away_rank"),
                home_rank=g.get("home_rank"),
                away_road_record=g.get("away_road_record"),
                home_home_record=g.get("home_home_record"),
                meta={
                    # `round` kept for backward compatibility with cached rows and any
                    # caller still reading meta; `round_name` is the field to use.
                    "round": espn_scoreboard.round_label(g, with_week=self.with_week)
                             or self.default_round,
                    "broadcast": g.get("broadcast"),
                    "neutral_site": g.get("neutral_site"),
                },
            ))
        return games

    def match_team(self, identifier: str | None) -> str | None:
        token = "".join(ch for ch in str(identifier or "").upper() if ch.isalnum())
        return token or None

    def opportunities(self, *, as_of: date,
                      scheduled_team_ids: Iterable[str] | None = None,
                      mode: OpportunityMode = OpportunityMode.SLATE,
                      limit: int = 8) -> list[Opportunity]:
        return []
