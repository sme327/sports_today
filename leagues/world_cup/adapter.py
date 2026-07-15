"""World Cup adapter: schedule-only.

No player opportunity analysis is connected; the adapter returns no opportunities
and the game view renders a schedule-only placeholder.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import pandas as pd

from domain.models import Opportunity, OpportunityMode, SlateGame
from leagues.base import register
from src.world_cup_api import schedule as world_cup_schedule


def _parse_start(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return pd.to_datetime(raw, utc=True).to_pydatetime()
    except Exception:
        return None


class WorldCupAdapter:
    league = "World Cup"
    emoji = "⚽"
    label = "⚽ World Cup"
    source_name = "ESPN World Cup"
    supports_deep_dive = False
    chip_label = "Match"

    def describe_game(self, game: SlateGame) -> str:
        parts = [game.meta.get("round") or "World Cup"]
        if game.venue:
            parts.append(game.venue)
        return " · ".join(parts)

    def fetch_schedule(self, slate_date: date) -> list[SlateGame]:
        games: list[SlateGame] = []
        for g in world_cup_schedule(slate_date):
            games.append(
                SlateGame(
                    league=self.league,
                    game_id=str(g.get("game_id")),
                    start_time=_parse_start(g.get("game_date")),
                    status=g.get("status"),
                    away_name=g.get("away"),
                    home_name=g.get("home"),
                    away_short=g.get("away_short"),
                    home_short=g.get("home_short"),
                    away_abbr=g.get("away_abbr"),
                    home_abbr=g.get("home_abbr"),
                    away_logo=g.get("away_logo"),
                    home_logo=g.get("home_logo"),
                    venue=g.get("venue"),
                    meta={
                        "round": g.get("round"),
                        "broadcast": g.get("broadcast"),
                    },
                )
            )
        return games

    def match_team(self, identifier: str | None) -> str | None:
        token = "".join(ch for ch in str(identifier or "").upper() if ch.isalnum())
        return token or None

    def opportunities(
        self,
        *,
        as_of: date,
        scheduled_team_ids: Iterable[str] | None = None,
        mode: OpportunityMode = OpportunityMode.SLATE,
        limit: int = 8,
    ) -> list[Opportunity]:
        return []


register(WorldCupAdapter())
