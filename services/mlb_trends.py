"""Confidence-building player trends for the MLB matchup page.

Two builders, both leakage-safe (``pa`` must be ``as_of``-bounded by the caller):

- ``pitcher_trend`` — a probable starter's per-start K's and hits-allowed over the
  recent window, season K%, trend direction, and the SP prop(s) we're serving.
- ``batter_trend`` — a hitter's per-game 1+-hit history (dots), L5/L10/L25 windows,
  current hit streak, and direction. The unit is per **game** (did they get a hit),
  which is what a "1+ Hit" pick actually rides on.

Everything is traceable to stored plate appearances — no fabrication.
"""

from __future__ import annotations

import pandas as pd

from domain.mlb_game_page import MLBBatterTrend, MLBPitcherTrend
from src.pitcher_opportunity import _per_start_lines, score_pitcher_opportunities

SPARK_STARTS = 8       # pitcher: recent starts to chart
BATTER_GAMES = 12      # batter: recent games to chart
BATTER_WINDOWS = (5, 10, 25)
MIN_STARTS = 3
MIN_GAMES = 5


def _headshot(pid: str) -> str:
    return (f"https://img.mlbstatic.com/mlb-photos/image/upload/w_120,q_auto:best/"
            f"v1/people/{pid}/headshot/67/current")


def _direction(series: list[float], lower_is_up: bool = False) -> str:
    """Compare the recent half of a chronological series to the earlier half."""
    if len(series) < 4:
        return "steady"
    half = len(series) // 2
    early, late = series[:-half], series[-half:]
    diff = (sum(late) / len(late)) - (sum(early) / len(early))
    if lower_is_up:
        diff = -diff
    if diff >= 0.75:
        return "up"
    if diff <= -0.75:
        return "down"
    return "steady"


# --------------------------------------------------------------- PITCHER ------
def pitcher_trend(pa: pd.DataFrame, pitcher_id: str) -> MLBPitcherTrend | None:
    sub = pa[pa["pitcher_id"].astype(str) == str(pitcher_id)]
    lines = _per_start_lines(sub)                       # newest → oldest, real starts only
    if len(lines) < MIN_STARTS:
        return None
    recent = lines.head(SPARK_STARTS).iloc[::-1]        # oldest → newest for the chart
    k_series = [int(v) for v in recent["k"]]
    hits_series = [int(v) for v in recent["hits"]]
    name = str(sub["pitcher_name"].iloc[-1])
    team = str(sub["pitching_team"].iloc[-1])
    k_pct = float(sub["is_strikeout"].mean()) if len(sub) else None

    props = []
    scored = score_pitcher_opportunities(pa, [str(pitcher_id)])
    for _, r in scored.iterrows():
        cleared = int(round(r["recent_hit_rate"] * r["starts"]))
        props.append(f"{r['market'].replace(' (SP)', '')} — {cleared} of last {int(r['starts'])}")

    return MLBPitcherTrend(
        pitcher_id=str(pitcher_id), name=name, team=team, headshot_url=_headshot(str(pitcher_id)),
        k_spark=tuple(k_series), hits_spark=tuple(hits_series),
        k_avg=round(sum(k_series) / len(k_series), 1),
        hits_avg=round(sum(hits_series) / len(hits_series), 1),
        k_pct=k_pct, k_dir=_direction(k_series), hits_dir=_direction(hits_series),
        starts=len(recent), props=tuple(props),
        caveat="Per-start form only — opponent lineup, park, and pitch count aren't modeled.",
    )


# --------------------------------------------------------------- BATTER -------
def _per_game_hits(pa_batter: pd.DataFrame) -> list[int]:
    """1 if the batter recorded ≥1 hit that game, else 0 — oldest → newest."""
    by_game = (pa_batter.groupby(["game_date", "game_id"])["is_hit"].max()
               .reset_index().sort_values(["game_date", "game_id"]))
    return [int(v) for v in by_game["is_hit"]]


def batter_trend(pa: pd.DataFrame, batter_id: str, category: str, tone: str,
                 line: str, support: list[str], risks: list[str]) -> MLBBatterTrend | None:
    sub = pa[pa["batter_id"].astype(str) == str(batter_id)]
    if sub.empty:
        return None
    games = _per_game_hits(sub)
    if len(games) < MIN_GAMES:
        return None
    windows = []
    for n in BATTER_WINDOWS:
        last = games[-n:]
        windows.append((f"L{n}", f"{sum(last)} / {len(last)}"))
    streak = 0
    for g in reversed(games):
        if g == 1:
            streak += 1
        else:
            break
    name = str(sub["batter_name"].iloc[-1])
    team = str(sub["batting_team"].iloc[-1])
    return MLBBatterTrend(
        player_id=str(batter_id), name=name, team=team, headshot_url=_headshot(str(batter_id)),
        category=category, tone=tone, dots=tuple(games[-BATTER_GAMES:]),
        windows=tuple(windows), hit_streak=streak, line=line,
        support=tuple(support[:2]), risks=tuple(risks[:2]),
    )
