"""Build SP strikeout + hits-allowed opportunities for a slate's probable starters.

Bridges the schedule's probable-pitcher names → stored ``pitcher_id`` (via
``match_pitcher``) → the pitcher scorer → normalized ``Opportunity`` objects that
flow into the same feed, ledger, and grading path as the batter props.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from domain.models import Opportunity, OpportunityMode
from services.mlb_analytics import match_pitcher
from src.pitcher_opportunity import score_pitcher_opportunities


def _headshot(pid: str) -> str:
    return (f"https://img.mlbstatic.com/mlb-photos/image/upload/w_120,q_auto:best/"
            f"v1/people/{pid}/headshot/67/current")


def build_pitcher_opportunities(pa: pd.DataFrame, probable_names: list[tuple[str, str]],
                                as_of: date, limit: int = 100_000) -> list[Opportunity]:
    """``probable_names`` = list of (pitcher_name, team_display). Returns scored SP
    strikeout + hits-allowed opportunities (empty if no data)."""
    if pa is None or pa.empty or not probable_names:
        return []
    ids = [pid for pid in (match_pitcher(pa, name) for name, _ in probable_names) if pid]
    if not ids:
        return []
    scored = score_pitcher_opportunities(pa, ids)
    if scored.empty:
        return []

    out: list[Opportunity] = []
    for _, r in scored.head(limit).iterrows():
        support = list(r.support) if isinstance(r.support, list) else []
        risks = list(r.risks) if isinstance(r.risks, list) else []
        out.append(Opportunity(
            league="MLB",
            player_id=str(r.pitcher_id),
            player_name=str(r.player),
            team_id=None,
            team_name=str(r.team),
            market=str(r.market),
            market_key=str(r.kind),
            direction=str(r.direction),
            threshold=int(r.threshold),
            opportunity_score=int(r.opportunity_score),
            stability_score=int(r.stability_score),
            supporting_evidence=support,
            negative_evidence=risks,
            image_url=None,                       # team logo stamped by the feed builder
            headshot_url=_headshot(str(r.pitcher_id)),
            mode=OpportunityMode.SLATE,
            components={"recent_avg": float(r.recent_avg),
                        "recent_hit_rate": float(r.recent_hit_rate),
                        "starts": float(r.starts)},
        ))
    return out
