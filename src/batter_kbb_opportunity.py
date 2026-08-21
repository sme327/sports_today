"""Batter strikeout and walk opportunity scoring.

Two per-game-count batter markets, built on the same reachable-bar discipline as
total bases (only offer a bar the batter actually reaches often) and sharing the
confirmed-lineup overlay. Both are **over-only and distinctive by design** — bars
that most batters clear (1+ K, staying under 2 K) are not opportunities, so they're
excluded; only a genuinely high-whiff or patient profile surfaces:

- **Batter strikeouts** — "2+ / 3+ Strikeouts": a high-strikeout batter. (1+ K is
  ~58% league-wide — too common to be a signal — and a contact hitter's "few Ks"
  overlaps the 1+ Hit market, so no under is offered.)
- **Batter walks** — "1+ / 2+ Walk": a patient, high-OBP hitter.

Leakage-safe: ``pa`` must already be ``as_of``-bounded by the caller. Every prop is
recorded/graded regardless of score; the Today feed's curation floor governs display.
"""

from __future__ import annotations

import pandas as pd

from src import lineup_overlay
from src.mlb_lineups import Lineups
from src.reliability import highest_reachable_over

_REQUIRED = {"batting_team", "batter_id", "batter_name", "game_date", "game_id",
             "is_strikeout", "is_walk"}

RECENT_GAMES = 20
MIN_GAMES = 10

K_THRESHOLDS = (2, 3)      # over only; 1+ K (~58% league) is too common to be a signal
K_FLOOR = 0.50             # cleared "t+ K" in ≥50% of recent games
BB_THRESHOLDS = (1, 2)
BB_FLOOR = 0.50

_RESULT_COLUMNS = ["batter_id", "player", "team", "market_key", "direction", "threshold",
                   "opportunity_score", "stability_score", "recent_avg", "recent_hit_rate",
                   "lineup_slot", "support", "risks"]


# How often a starting batter actually reaches each strikeout bar, measured over 34,110
# starter batter-games. Used as impressiveness — how *hard* the bar is — rather than
# `threshold / max(thresholds)`, which was a constant in practice: the 3+ bar is never
# reachable (nobody clears it in half their games), so **100% of picks are the 2+ bar**
# and the old term ranked nothing while capping the scale at 75.
_K_BASE = {2: 0.218, 3: 0.046}

# The scorer's own risk line always said strikeouts swing with the opposing starter, and
# it was right: within the population this scorer would offer, the batter's own clear rate
# carries an AUC of 0.515 — noise — while the opposing starter's prior strikeout rate
# carries 0.566. The reachable-bar filter does the work (+14.0 pp on its own) and the
# score added nothing after it. v2 folds the pitcher in; out of sample that moves AUC
# 0.519 -> 0.583 and the served population from 4 props to 85 at +25.3 over base.
#
# Not a contradiction of `batter-hit-v4`, which rejected the opposing starter for *hits*:
# strikeouts are pitcher-driven in a way that hits are not, and both were measured.
_SP_NEUTRAL = 0.5           # what we assume when the probable starter is unknown
_SP_MIN_BF = 60             # batters faced before a starter's rate means anything
# An unassessed matchup is scored neutrally — we cannot rank it down on merit we never
# measured — so the doubt lands on *stability* instead, which is the number that says how
# much to trust the rank. Without it the highest-scoring prop on a slate can be the one
# whose driving factor is unknown, which is precisely backwards.
_UNKNOWN_SP_STABILITY_CAP = 58


def starter_k_rates(pa: pd.DataFrame) -> dict[str, float]:
    """Each pitcher's strikeouts per batter faced, from the (already as_of-bounded) feed."""
    if pa.empty or "pitcher_id" not in pa.columns:
        return {}
    g = pa.groupby("pitcher_id")["is_strikeout"].agg(["sum", "size"])
    g = g[g["size"] >= _SP_MIN_BF]
    return {str(pid): float(row["sum"] / row["size"]) for pid, row in g.iterrows()}


def _sp_term(rate: float | None, lo: float, hi: float) -> float:
    """The opposing starter's strikeout rate on a 0-1 scale, league-relative.

    ``None`` (no probable posted, or too few batters faced) returns neutral rather than
    zero — an unknown matchup is not a favourable one, and it should not be scored as if
    the pitcher were the softest in the league.
    """
    if rate is None or hi <= lo:
        return _SP_NEUTRAL
    return max(0.0, min(1.0, (rate - lo) / (hi - lo)))


def _reliable_over(values: pd.Series, thresholds, floor: float):
    """(threshold, clear_rate, impressiveness) for the highest bar cleared ≥ floor."""
    picked = highest_reachable_over(values, thresholds, floor)
    if picked is None:
        return None
    thr, clear = picked
    return thr, clear, thr / max(thresholds)


def _score(clear: float, impressiveness: float, n: int, imp_weight: float = 0.25) -> int:
    # Walks still use the v1 shape. Strikeouts use `_score_k` below.
    rel_weight = 0.90 - imp_weight
    s = 100 * (rel_weight * clear + imp_weight * impressiveness + 0.10 * min(n / RECENT_GAMES, 1.0))
    return max(0, min(round(s), 100))


def _score_k(clear: float, threshold: int, sp: float, n: int) -> int:
    """batter-k-v2 — the opposing starter carries real weight.

    Weighted toward the matchup because that is where the signal is: after the
    reachable-bar filter, the batter's own clear rate is noise (AUC 0.515) and the
    opposing starter is not (0.566). Impressiveness is the bar's measured rarity, so it
    stops being a constant that only shifted the scale down.
    """
    impressiveness = 1.0 - _K_BASE.get(threshold, 0.2)
    s = 100 * (0.45 * clear + 0.35 * sp + 0.10 * impressiveness
               + 0.10 * min(n / RECENT_GAMES, 1.0))
    return max(0, min(round(s), 100))


def _stability(clear: float, n: int) -> int:
    return max(0, min(round(45 + min(n, RECENT_GAMES) * 1.2 + clear * 15), 100))


def _per_game(pa: pd.DataFrame, teams: list[str]) -> pd.DataFrame | None:
    if pa.empty or not _REQUIRED.issubset(pa.columns) or not teams:
        return None
    x = pa.loc[pa["batting_team"].isin(teams)]
    if x.empty:
        return None
    return (x.groupby(["batter_id", "game_date", "game_id"])
            .agg(k=("is_strikeout", "sum"), bb=("is_walk", "sum"))
            .reset_index())


def _name_team(x: pd.DataFrame, per_game: pd.DataFrame, batter_id) -> tuple[str, str]:
    sub = x.loc[x["batter_id"] == batter_id]
    return str(sub["batter_name"].iloc[-1]), str(sub["batting_team"].iloc[-1])


def score_k_opportunities(pa: pd.DataFrame, teams: list[str], minimum_games: int = MIN_GAMES,
                          lineups: Lineups | None = None,
                          opposing_starters: dict[str, str] | None = None) -> pd.DataFrame:
    """Over-only batter-strikeout props (2+/3+ K), weighted by the opposing starter.

    ``opposing_starters`` maps a raw PBP batting-team name to the pitcher id it faces —
    resolved by the adapter, because `src/` is a leaf and cannot reach the schedule. A
    team without a resolved probable is scored neutrally on the matchup and says so.
    """
    per_game = _per_game(pa, teams)
    if per_game is None:
        return pd.DataFrame(columns=_RESULT_COLUMNS)
    x = pa.loc[pa["batting_team"].isin(teams)]
    opposing_starters = opposing_starters or {}
    rates = starter_k_rates(pa)
    spread = sorted(rates.values())
    lo = spread[int(len(spread) * 0.10)] if spread else 0.0
    hi = spread[int(len(spread) * 0.90)] if spread else 0.0
    rows = []
    for batter_id, g in per_game.groupby("batter_id"):
        recent = g.sort_values("game_date").tail(RECENT_GAMES)["k"]
        n = len(recent)
        if n < minimum_games:
            continue
        over = _reliable_over(recent, K_THRESHOLDS, K_FLOOR)
        if not over:
            continue
        thr, clear, imp = over
        avg = float(recent.mean())
        name, team = _name_team(x, per_game, batter_id)
        cleared = int(round(clear * n))
        sp_id = opposing_starters.get(team)
        sp_rate = rates.get(str(sp_id)) if sp_id else None
        sp = _sp_term(sp_rate, lo, hi)
        support = [f"{avg:.1f} strikeouts per game over last {n}",
                   f"{thr}+ K in {cleared} of {n} games"]
        risks = []
        if sp_rate is None:
            # Named first: without the probable, the term that carries this market's
            # signal is missing, and the score is deliberately neutral on it.
            risks.append("Opposing starter not posted — the matchup, which drives this "
                         "market more than the batter does, is unassessed")
        elif sp <= 0.35:
            risks.append(f"Faces a low-strikeout starter ({sp_rate:.0%} of batters faced) "
                         f"— the biggest single argument against this prop")
        else:
            support.append(f"Opposing starter strikes out {sp_rate:.0%} of batters faced")
        risks.append("Strikeouts swing with the opposing starter and two-strike counts")
        stability = _stability(clear, n)
        if sp_rate is None:
            stability = min(stability, _UNKNOWN_SP_STABILITY_CAP)
        rows.append(_row(batter_id, name, team, "batter_k", "over", thr,
                         _score_k(clear, thr, sp, n), stability, avg, clear,
                         support, risks, lineups))
    return _frame(rows)



def _row(batter_id, name, team, key, direction, thr, score, stability, avg, clear,
         support, risks, lineups) -> dict:
    score, stability, slot, _posted, _raw = lineup_overlay.apply(
        batter_id, team, score, stability, support, risks, lineups)
    return {"batter_id": int(batter_id), "player": name, "team": team,
            "market_key": key, "direction": direction, "threshold": thr,
            "opportunity_score": score, "stability_score": stability,
            "recent_avg": round(avg, 2), "recent_hit_rate": round(clear, 3),
            "lineup_slot": slot, "support": support[:3], "risks": risks[:2]}


def _frame(rows: list[dict]) -> pd.DataFrame:
    result = pd.DataFrame(rows, columns=_RESULT_COLUMNS)
    if result.empty:
        return result
    return result.sort_values(["opportunity_score", "stability_score"],
                              ascending=False).reset_index(drop=True)
