"""NFL adapter: ESPN scoreboard for the schedule, ingested vendor seasons for props."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Iterable

import pandas as pd

from domain.models import Opportunity, OpportunityMode
from leagues._espn_schedule import ScheduleOnlyESPN
from leagues.base import register
from src.config import DB_PATH


class NFLAdapter(ScheduleOnlyESPN):
    league = "NFL"
    emoji = "🏈"
    label = "🏈 NFL"
    source_name = "ESPN NFL"
    espn_path = "football/nfl"
    with_week = True            # "Preseason · Wk 2"
    default_round = "NFL"
    # NFL *can* deep-dive, but only for a game the ingested season feed actually covers.
    # Whether a given game qualifies is decided per game by `deep_dive_available`, so a
    # card never offers a link that lands on "not connected".
    supports_deep_dive = True

    def deep_dive_available(self, game) -> bool:
        from services.nfl_bridge import has_deep_dive
        return has_deep_dive(game)

    def opportunities(
        self,
        *,
        as_of: date,
        scheduled_team_ids: Iterable[str] | None = None,
        mode: OpportunityMode = OpportunityMode.SLATE,
        limit: int = 8,
    ) -> list[Opportunity]:
        """Player props from the ingested season feeds.

        **Leakage-safe by query, not by trust**: only games strictly before ``as_of`` are
        loaded, so a prop can never be scored on the game it predicts.

        Returns ``[]`` freely — before the ingested season reaches the current week there
        is no prior form to score, which is the honest answer rather than a stale one.
        """
        prior = _load_player_games(as_of)
        if prior.empty or _is_stale(prior, as_of):
            return []
        teams = None if mode is OpportunityMode.LEAGUE_WIDE else {
            str(t) for t in (scheduled_team_ids or []) if t}
        if teams is not None and not teams:
            return []

        from src.nfl_opportunity import score_nfl_opportunities
        scored = score_nfl_opportunities(prior, teams)
        if scored.empty:
            return []

        out: list[Opportunity] = []
        for row in scored.head(limit).itertuples():
            out.append(Opportunity(
                league=self.league,
                player_id=str(row.player_id),
                player_name=str(row.player),
                team_id=None,
                team_name=str(row.team),
                market=str(row.market),
                market_key=str(row.market_key),
                direction="over",
                threshold=row.threshold,
                opportunity_score=int(row.opportunity_score),
                stability_score=int(row.stability_score),
                supporting_evidence=list(row.support),
                negative_evidence=list(row.risks),
                recent_line=list(row.recent_line),
                line_threshold=float(row.threshold),
                mode=mode,
                components={"clear_rate": float(row.clear_rate),
                            "recent_avg": float(row.recent_avg),
                            "games": float(row.games)},
            ))
        return out


_PROP_COLUMNS = ("player_id", "player", "team", "position", "game_date", "season", "week",
                 "passing_yds", "rushing_yds", "receiving_yds", "receiving_rec",
                 "rushing_att")


# An NFL offseason is seven months of trades, retirements and depth-chart churn. Scoring
# an August preseason game off January's games would produce a confident-looking
# "10+ carries" for a back who may not be on the roster — the failure the honest-data rule
# exists to prevent. Six weeks is roughly a bye plus a month: long enough to survive the
# vendor feed arriving a week late mid-season, short enough that an offseason never passes.
_MAX_STALE_DAYS = 42


def _is_stale(prior: pd.DataFrame, as_of: date) -> bool:
    """Whether the newest ingested game is too old to describe current form."""
    if "game_date" not in prior.columns or prior.empty:
        return True
    latest = str(prior["game_date"].max() or "")
    try:
        return (as_of - date.fromisoformat(latest[:10])).days > _MAX_STALE_DAYS
    except ValueError:
        return True


def _load_player_games(as_of: date, db_path=DB_PATH) -> pd.DataFrame:
    """Ingested player games strictly before ``as_of``. Empty when nothing is loaded."""
    if not db_path.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            return pd.read_sql_query(
                f"SELECT {', '.join(_PROP_COLUMNS)} FROM nfl_player_games "
                f"WHERE game_date < ? ORDER BY player_id, game_date",
                conn, params=(as_of.isoformat(),))
    except Exception:                      # noqa: BLE001 — no table yet is not an error
        return pd.DataFrame()


register(NFLAdapter())
