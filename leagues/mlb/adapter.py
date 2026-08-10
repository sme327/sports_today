"""MLB adapter: schedule normalization, team matching, and 1+ hit opportunities."""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import pandas as pd

from domain.models import Opportunity, OpportunityMode, SlateGame
from leagues.base import register
from leagues.mlb.teams import canonical_team
from services.data_access import load_plate_appearances
from services.mlb_analytics import match_pitcher
from src import mlb_injuries
from src.availability import InjuryReport
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
                    away_score=g.get("away_score"),
                    home_score=g.get("home_score"),
                    state=g.get("state"),
                    winner=g.get("winner"),
                    status_detail=g.get("status_detail"),
                    season=g.get("season"),
                    phase=g.get("phase"),
                    round_name=g.get("series_description"),
                    series_game=g.get("series_game"),
                    series_total=g.get("series_total"),
                    series_summary=g.get("series_summary"),
                    series_leader_wins=g.get("series_leader_wins"),
                    series_trailing_wins=g.get("series_trailing_wins"),
                    away_record=g.get("away_record"),
                    home_record=g.get("home_record"),
                    meta={
                        "away_pitcher": g.get("away_pitcher"),
                        "home_pitcher": g.get("home_pitcher"),
                    },
                )
            )
        return games

    def match_team(self, identifier: str | None) -> str | None:
        return canonical_team(identifier)

    def _slate_availability(self, slate_date: date, teams: list[str]) -> InjuryReport:
        """Roster availability for the teams on this slate (empty when unavailable)."""
        try:
            games = self.fetch_schedule(slate_date)
        except Exception:
            return InjuryReport()
        canon = {canonical_team(t) for t in teams}
        ids = {g.away_id for g in games if canonical_team(g.away_name) in canon}
        ids |= {g.home_id for g in games if canonical_team(g.home_name) in canon}
        return mlb_injuries.fetch_teams(sorted(i for i in ids if i))

    def _opposing_starters(self, pa: pd.DataFrame, slate_date: date,
                           teams: list[str]) -> dict[str, str]:
        """Map each raw PBP batting-team name to the id of the pitcher it faces.

        Resolved here rather than in the scorer because `src/` is a leaf layer and
        cannot reach the schedule or `match_pitcher`. A probable that does not
        resolve is simply absent, and the scorer then says nothing about the matchup
        rather than guessing.
        """
        out: dict[str, str] = {}
        try:
            games = self.fetch_schedule(slate_date)
        except Exception:
            return out
        by_canon = {canonical_team(name): name for name in teams}
        for game in games:
            for own, opp_key in ((game.away_name, "home_pitcher"),
                                 (game.home_name, "away_pitcher")):
                raw = by_canon.get(canonical_team(own))
                probable = (game.meta or {}).get(opp_key)
                if not raw or not probable or str(probable).upper() == "TBD":
                    continue
                pid = match_pitcher(pa, str(probable))
                if pid:
                    out[raw] = pid
        return out

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

        # Today's posted lineups (cached, degrades to empty offline). Slot + bench
        # awareness lifts confirmed hitters and demotes anyone scratched pregame.
        lineups = None
        try:
            from services.app_cache import cached_lineups
            lineups = cached_lineups(as_of.isoformat())
        except Exception:
            lineups = None

        availability = self._slate_availability(as_of, teams)
        opposing = self._opposing_starters(pa, as_of, teams)
        scored = score_hit_opportunities(pa, teams, lineups=lineups,
                                         opposing_starters=opposing,
                                         availability=availability)
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
                    market_key="batter_hit",
                    direction="over",
                    threshold=1,
                    opportunity_score=int(row.opportunity_score),
                    stability_score=int(row.stability_score),
                    supporting_evidence=support,
                    negative_evidence=risks,
                    image_url=None,  # stamped with team logo by the feed builder
                    headshot_url=(f"https://img.mlbstatic.com/mlb-photos/image/upload/"
                                  f"w_120,q_auto:best/v1/people/{int(row.batter_id)}/headshot/67/current"),
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

    def tb_opportunities(self, *, as_of: date,
                         scheduled_team_ids: Iterable[str] | None = None,
                         limit: int = 8) -> list[Opportunity]:
        """Batter Total-Bases opportunities for the slate's teams — same feed /
        ledger / grading path as 1+ Hit, with the same confirmed-lineup overlay."""
        from domain.markets import format_market
        from src.tb_opportunity import score_tb_opportunities

        pa = load_plate_appearances(as_of=as_of)
        if pa.empty:
            return []
        canon_set = {c for c in (canonical_team(t) for t in (scheduled_team_ids or [])) if c}
        if not canon_set:
            return []
        teams = self._raw_team_names(pa, canon_set)
        if not teams:
            return []
        lineups = None
        try:
            from services.app_cache import cached_lineups
            lineups = cached_lineups(as_of.isoformat())
        except Exception:
            lineups = None

        scored = score_tb_opportunities(pa, teams, lineups=lineups)
        if scored.empty:
            return []

        out: list[Opportunity] = []
        for _, row in scored.head(limit).iterrows():
            thr = int(row.threshold)
            out.append(Opportunity(
                league=self.league,
                player_id=str(int(row.batter_id)),
                player_name=str(row.player),
                team_id=None,
                team_name=str(row.team),
                market=format_market("batter_tb", thr, "over"),
                market_key="batter_tb",
                direction="over",
                threshold=thr,
                opportunity_score=int(row.opportunity_score),
                stability_score=int(row.stability_score),
                supporting_evidence=list(row.support) if isinstance(row.support, list) else [],
                negative_evidence=list(row.risks) if isinstance(row.risks, list) else [],
                image_url=None,
                headshot_url=(f"https://img.mlbstatic.com/mlb-photos/image/upload/"
                              f"w_120,q_auto:best/v1/people/{int(row.batter_id)}/headshot/67/current"),
                mode=OpportunityMode.SLATE,
                components={"recent_avg": float(row.recent_avg),
                            "recent_hit_rate": float(row.recent_hit_rate)},
            ))
        return out

    def k_bb_opportunities(self, *, as_of: date,
                           scheduled_team_ids: Iterable[str] | None = None,
                           limit: int = 8) -> list[Opportunity]:
        """Batter strikeout (two-directional) + walk (over) opportunities for the
        slate's teams — same feed / ledger / grading path and lineup overlay as 1+ Hit."""
        from domain.markets import format_market
        from src.batter_kbb_opportunity import score_bb_opportunities, score_k_opportunities

        pa = load_plate_appearances(as_of=as_of)
        if pa.empty:
            return []
        canon_set = {c for c in (canonical_team(t) for t in (scheduled_team_ids or [])) if c}
        if not canon_set:
            return []
        teams = self._raw_team_names(pa, canon_set)
        if not teams:
            return []
        lineups = None
        try:
            from services.app_cache import cached_lineups
            lineups = cached_lineups(as_of.isoformat())
        except Exception:
            lineups = None

        out: list[Opportunity] = []
        for scorer in (score_k_opportunities, score_bb_opportunities):
            scored = scorer(pa, teams, lineups=lineups)
            for _, row in scored.head(limit).iterrows():
                thr, key, direction = int(row.threshold), str(row.market_key), str(row.direction)
                out.append(Opportunity(
                    league=self.league,
                    player_id=str(int(row.batter_id)),
                    player_name=str(row.player),
                    team_id=None,
                    team_name=str(row.team),
                    market=format_market(key, thr, direction),
                    market_key=key,
                    direction=direction,
                    threshold=thr,
                    opportunity_score=int(row.opportunity_score),
                    stability_score=int(row.stability_score),
                    supporting_evidence=list(row.support) if isinstance(row.support, list) else [],
                    negative_evidence=list(row.risks) if isinstance(row.risks, list) else [],
                    image_url=None,
                    headshot_url=(f"https://img.mlbstatic.com/mlb-photos/image/upload/"
                                  f"w_120,q_auto:best/v1/people/{int(row.batter_id)}/headshot/67/current"),
                    mode=OpportunityMode.SLATE,
                    components={"recent_avg": float(row.recent_avg),
                                "recent_hit_rate": float(row.recent_hit_rate)},
                ))
        return out


register(MLBAdapter())
