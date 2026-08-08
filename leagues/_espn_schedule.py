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
    with_week: bool = False      # append "· Wk N" (football/college)
    rank_prefix: bool = False    # prepend "#N " to ranked teams (NCAA)
    default_round: str = ""      # round label when the source omits one

    def describe_game(self, game: SlateGame) -> str:
        parts = [game.meta.get("round") or self.default_round]
        if game.venue:
            parts.append(game.venue)
        return " · ".join(p for p in parts if p)

    def fetch_schedule(self, slate_date: date) -> list[SlateGame]:
        games: list[SlateGame] = []
        for g in espn_scoreboard.fetch(self.espn_path, slate_date):
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
                meta={
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
