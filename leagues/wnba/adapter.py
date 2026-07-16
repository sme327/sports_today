"""WNBA adapter: schedule normalization and points/rebounds/assists opportunities.

Game deep-dive analysis is not connected yet, so ``supports_deep_dive`` is False;
the game view renders a schedule-only placeholder for WNBA.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import pandas as pd

from domain.models import Opportunity, OpportunityMode, SlateGame
from leagues.base import register
from services.data_access import load_wnba_player_logs
from src.wnba_api import schedule as wnba_schedule
from src.wnba_opportunity import score_wnba_opportunities

SCORING_ENGINE_VERSION = "wnba-pra-v0.1"


def _normalize(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _parse_start(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return pd.to_datetime(raw, utc=True).to_pydatetime()
    except Exception:
        return None


class WNBAAdapter:
    league = "WNBA"
    emoji = "🏀"
    label = "🏀 WNBA"
    source_name = "ESPN WNBA"
    supports_deep_dive = False
    chip_label = "Schedule"

    def describe_game(self, game: SlateGame) -> str:
        venue = game.venue or "Venue TBD"
        broadcast = game.meta.get("broadcast") or ""
        return venue if not broadcast else f"{venue} · {broadcast}"

    def fetch_schedule(self, slate_date: date) -> list[SlateGame]:
        games: list[SlateGame] = []
        for g in wnba_schedule(slate_date):
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
                    away_score=g.get("away_score"),
                    home_score=g.get("home_score"),
                    state=g.get("state"),
                    winner=g.get("winner"),
                    status_detail=g.get("status_detail"),
                    meta={"broadcast": g.get("broadcast")},
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
        logs = load_wnba_player_logs(as_of=as_of)
        if logs.empty:
            return []

        if mode is OpportunityMode.LEAGUE_WIDE:
            teams = set()
            for column in ("team_abbr", "team_id", "team"):
                if column in logs.columns:
                    teams.update(logs[column].dropna().astype(str).unique())
        else:
            teams = {str(t) for t in (scheduled_team_ids or []) if t}
        if not teams:
            return []

        scored = score_wnba_opportunities(logs, teams)
        if scored.empty:
            return []

        out: list[Opportunity] = []
        for _, row in scored.head(limit).iterrows():
            support = list(row.support) if isinstance(row.support, list) else []
            risks = list(row.risks) if isinstance(row.risks, list) else []
            headshot = row.headshot if isinstance(row.headshot, str) and row.headshot else None
            out.append(
                Opportunity(
                    league=self.league,
                    player_id=str(row.player_id),
                    player_name=str(row.player),
                    team_id=str(row.team_id) if row.team_id else None,
                    team_name=str(row.team),
                    market=str(row.display_market),
                    threshold=row.threshold,
                    opportunity_score=int(row.opportunity_score),
                    stability_score=int(row.stability_score),
                    supporting_evidence=support,
                    negative_evidence=risks,
                    image_url=None,          # team logo stamped by the feed builder
                    headshot_url=headshot,   # player headshot for the merged avatar
                    mode=mode,
                    components={
                        "minutes_l5": float(row.minutes_l5),
                        "minutes_l10": float(row.minutes_l10),
                        "average_l5": float(row.average_l5),
                        "average_l10": float(row.average_l10),
                        "hit_rate_l5": float(row.hit_rate_l5),
                        "hit_rate_l10": float(row.hit_rate_l10),
                    },
                )
            )
        return out


register(WNBAAdapter())
