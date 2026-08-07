"""Batter total-bases opportunity scoring ("N+ Total Bases").

Total bases is a per-game count (sum of ``total_bases`` across a batter's plate
appearances that game). Like the WNBA/pitcher scorers, the threshold is chosen from
the batter's own recent per-game distribution — the highest bar he clears often
enough to be meaningful — never from betting lines (we ingest no odds). Shares the
confirmed-lineup overlay with the 1+ Hit scorer. Leakage-safe: ``pa`` must already
be ``as_of``-bounded by the caller.
"""

from __future__ import annotations

import pandas as pd

from src import lineup_overlay
from src.mlb_lineups import Lineups

_REQUIRED = {"batting_team", "batter_id", "batter_name", "game_date", "game_id", "total_bases"}

TB_THRESHOLDS = (1, 2, 3, 4)     # over only; 1 is excluded as trivial (any hit clears it)
RECENT_GAMES = 20
MIN_GAMES = 8
# v2 (ledger-refit): the old impressiveness-weighting chose the *impressive* bar over
# the *reachable* one — 83% of TB picks had a recent clear-rate < 0.35 and hit only
# ~21%, while picks cleared in ≥half of recent games hit far better. So a TB over is
# only offered on a bar the batter actually reaches often; batters who reach none are
# skipped rather than handed a low-probability pick.
MIN_CLEAR = 0.50

_RESULT_COLUMNS = ["batter_id", "player", "team", "market_key", "direction", "threshold",
                   "opportunity_score", "stability_score", "recent_avg", "recent_hit_rate",
                   "lineup_slot", "support", "risks"]


def _score(hit_rate: float, impressiveness: float, n: int) -> int:
    # Reliability-first: the recent clear-rate carries most of the score, with a
    # modest bonus for a higher (more impressive) bar and for sample depth.
    s = 100 * (0.70 * hit_rate + 0.15 * impressiveness + 0.15 * min(n / RECENT_GAMES, 1.0))
    return max(0, min(round(s), 100))


def _best_threshold(values: pd.Series) -> dict | None:
    """The highest TB bar the batter clears in at least ``MIN_CLEAR`` of recent games —
    a meaningful *and reachable* over. Returns ``None`` when no bar clears the floor
    (no honest TB over for this batter), so the market simply skips him."""
    lo, hi = min(TB_THRESHOLDS), max(TB_THRESHOLDS)
    span = (hi - lo) or 1
    n = len(values)
    reliable = [(t, float((values >= t).mean())) for t in TB_THRESHOLDS if t > lo
                if float((values >= t).mean()) >= MIN_CLEAR]
    if not reliable:
        return None
    thr, rate = max(reliable, key=lambda x: x[0])   # highest reliably-cleared bar
    return {"threshold": thr, "hit_rate": rate, "impressiveness": (thr - lo) / span,
            "avg": float(values.mean()), "n": n}


def score_tb_opportunities(pa: pd.DataFrame, teams: list[str], minimum_games: int = MIN_GAMES,
                           lineups: Lineups | None = None) -> pd.DataFrame:
    if pa.empty or not _REQUIRED.issubset(pa.columns) or not teams:
        return pd.DataFrame(columns=_RESULT_COLUMNS)
    x = pa.loc[pa["batting_team"].isin(teams)]
    per_game = (x.groupby(["batter_id", "game_date", "game_id"])["total_bases"]
                .sum().reset_index())
    rows = []
    for batter_id, g in per_game.groupby("batter_id"):
        recent = g.sort_values("game_date").tail(RECENT_GAMES)
        if len(recent) < minimum_games:
            continue
        d = _best_threshold(recent["total_bases"])
        if d is None:            # no reachable TB bar → not a TB opportunity
            continue
        thr, n, avg, hit = d["threshold"], d["n"], d["avg"], d["hit_rate"]
        cleared = int(round(hit * n))
        name = str(x.loc[x["batter_id"] == batter_id, "batter_name"].iloc[-1])
        team = str(x.loc[x["batter_id"] == batter_id, "batting_team"].iloc[-1])

        score = _score(hit, d["impressiveness"], n)
        stability = max(0, min(round(45 + min(n, RECENT_GAMES) * 1.2 + hit * 15), 100))
        support = [f"{avg:.1f} total bases per game over last {n}",
                   f"Reached {thr}+ in {cleared} of {n} games"]
        risks: list[str] = []
        team_name = team
        score, stability, slot, team_posted = lineup_overlay.apply(
            batter_id, team_name, score, stability, support, risks, lineups)
        if not risks:
            risks.append("Total bases swing with extra-base variance and opposing pitching")

        rows.append({
            "batter_id": int(batter_id), "player": name, "team": team,
            "market_key": "batter_tb", "direction": "over", "threshold": thr,
            "opportunity_score": score, "stability_score": stability,
            "recent_avg": round(avg, 2), "recent_hit_rate": round(hit, 3),
            "lineup_slot": slot, "support": support[:3], "risks": risks[:2]})
    result = pd.DataFrame(rows, columns=_RESULT_COLUMNS)
    if result.empty:
        return result
    return result.sort_values(["opportunity_score", "stability_score"],
                              ascending=False).reset_index(drop=True)
