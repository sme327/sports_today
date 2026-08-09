"""MLS adapter: real schedule from ESPN (usa.1), with a deep-dive matchup page.

``supports_deep_dive = True`` — opening an MLS game routes to the MLS matchup
page (views/mls_game.py). The schedule carries genuinely real extras the page
uses without any fabrication: W-D-L records, recent form, brand colors, the
competition label, and the broadcast. Player-opportunity scoring is not built
yet (no soccer stats pipeline), so ``opportunities`` returns [].
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import pandas as pd

from domain.models import Opportunity, OpportunityMode, SlateGame
from leagues.base import register
from src import espn_soccer
from src.espn_scoreboard import season_phase


def _normalize(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _parse_start(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return pd.to_datetime(raw, utc=True).to_pydatetime()
    except Exception:
        return None


class MLSAdapter:
    league = "MLS"
    emoji = "⚽"
    label = "⚽ MLS"
    source_name = "ESPN MLS"
    supports_deep_dive = True
    chip_label = "Matchup"

    def describe_game(self, game: SlateGame) -> str:
        parts = [game.meta.get("competition") or "MLS"]
        if game.venue:
            parts.append(game.venue)
        return " · ".join(parts)

    def fetch_schedule(self, slate_date: date) -> list[SlateGame]:
        games: list[SlateGame] = []
        for g in espn_soccer.schedule(espn_soccer.MLS, slate_date):
            games.append(
                SlateGame(
                    league=self.league,
                    game_id=str(g.get("game_id")),
                    start_time=_parse_start(g.get("game_date")),
                    status=g.get("status"),
                    away_id=g.get("away_id"),
                    home_id=g.get("home_id"),
                    away_name=g.get("away"),
                    home_name=g.get("home"),
                    away_short=g.get("away_short"),
                    home_short=g.get("home_short"),
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
                    season=g.get("season_year"),
                    phase=season_phase(g.get("season_slug"), g.get("season_type")),
                    competition=g.get("competition"),
                    meta={
                        "competition": g.get("competition"),
                        "broadcast": g.get("broadcast"),
                        "away_record": g.get("away_record"),
                        "home_record": g.get("home_record"),
                        "away_form": g.get("away_form"),
                        "home_form": g.get("home_form"),
                        "away_color": g.get("away_color"),
                        "home_color": g.get("home_color"),
                    },
                )
            )
        return games

    def match_team(self, identifier: str | None) -> str | None:
        token = _normalize(identifier)
        return token or None

    def opportunities(
        self,
        *,
        as_of: date,
        scheduled_team_ids: Iterable[str] | None = None,
        mode: OpportunityMode = OpportunityMode.SLATE,
        limit: int = 8,
    ) -> list[Opportunity]:
        # No soccer player-stats pipeline yet; opportunities are intentionally empty.
        return []


register(MLSAdapter())
