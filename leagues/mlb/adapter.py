"""MLB adapter: schedule normalization, team matching, and 1+ hit opportunities."""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import pandas as pd

from domain.models import Opportunity, OpportunityMode, SlateGame
from leagues.base import register
from leagues.mlb.teams import canonical_team
from services.data_access import load_plate_appearances
from src.mlb_api import schedule as mlb_schedule
from src.opportunity import score_hit_opportunities

SCORING_ENGINE_VERSION = "mlb-1hit-v0.1"


def _parse_start(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return pd.to_datetime(raw, utc=True).to_pydatetime()
    except Exception:
        return None


class MLBAdapter:
    league = "MLB"
    emoji = "⚾️"
    label = "⚾️ MLB"
    source_name = "MLB StatsAPI"
    supports_deep_dive = True
    chip_label = "Analysis"

    def describe_game(self, game: SlateGame) -> str:
        away_p = game.meta.get("away_pitcher") or "TBD"
        home_p = game.meta.get("home_pitcher") or "TBD"
        return f"{away_p} vs {home_p}"

    def fetch_schedule(self, slate_date: date) -> list[SlateGame]:
        games: list[SlateGame] = []
        for g in mlb_schedule(slate_date):
            games.append(
                SlateGame(
                    league=self.league,
                    game_id=str(g.get("game_pk")),
                    start_time=_parse_start(g.get("game_date")),
                    status=g.get("status"),
                    away_id=str(g.get("away_id")) if g.get("away_id") else None,
                    home_id=str(g.get("home_id")) if g.get("home_id") else None,
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
                        "away_pitcher": g.get("away_pitcher"),
                        "home_pitcher": g.get("home_pitcher"),
                    },
                )
            )
        return games

    def match_team(self, identifier: str | None) -> str | None:
        return canonical_team(identifier)

    def _raw_team_names(self, pa: pd.DataFrame, canon_set: set[str] | None) -> list[str]:
        """Raw PBP team strings, optionally restricted to a canonical set."""
        if pa.empty or "batting_team" not in pa.columns:
            return []
        names = pa["batting_team"].dropna().astype(str).unique()
        if canon_set is None:
            return sorted(names)
        return sorted(n for n in names if canonical_team(n) in canon_set)

    def opportunities(
        self,
        *,
        as_of: date,
        scheduled_team_ids: Iterable[str] | None = None,
        mode: OpportunityMode = OpportunityMode.SLATE,
        limit: int = 8,
    ) -> list[Opportunity]:
        pa = load_plate_appearances(as_of=as_of)
        if pa.empty:
            return []

        if mode is OpportunityMode.LEAGUE_WIDE:
            teams = self._raw_team_names(pa, None)
        else:
            canon_set = {
                c for c in (canonical_team(t) for t in (scheduled_team_ids or [])) if c
            }
            if not canon_set:
                return []
            teams = self._raw_team_names(pa, canon_set)
        if not teams:
            return []

        scored = score_hit_opportunities(pa, teams)
        if scored.empty:
            return []

        out: list[Opportunity] = []
        for _, row in scored.head(limit).iterrows():
            support = list(row.support) if isinstance(row.support, list) else []
            risks = list(row.risks) if isinstance(row.risks, list) else []
            out.append(
                Opportunity(
                    league=self.league,
                    player_id=str(int(row.batter_id)),
                    player_name=str(row.player),
                    team_id=None,
                    team_name=str(row.team),
                    market="1+ Hit",
                    threshold=1,
                    opportunity_score=int(row.opportunity_score),
                    stability_score=int(row.stability_score),
                    supporting_evidence=support,
                    negative_evidence=risks,
                    image_url=None,  # stamped with team logo by the feed builder
                    mode=mode,
                    components={
                        "last_25_hit_rate": float(row.last_25_hit_rate),
                        "last_50_hit_rate": float(row.last_50_hit_rate),
                        "pa_per_game": float(row.pa_per_game),
                        "k_rate": float(row.k_rate),
                    },
                )
            )
        return out


register(MLBAdapter())
