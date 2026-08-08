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


def _reliable_over(values: pd.Series, thresholds, floor: float):
    """(threshold, clear_rate, impressiveness) for the highest bar cleared ≥ floor."""
    hi = max(thresholds)
    ok = [(t, float((values >= t).mean()), t / hi) for t in thresholds
          if float((values >= t).mean()) >= floor]
    return max(ok, key=lambda x: x[0]) if ok else None


def _score(clear: float, impressiveness: float, n: int, imp_weight: float = 0.25) -> int:
    # Reliability-first, but impressiveness weighted enough that a distinctive bar
    # outranks a trivial one (which then sits below the Today curation floor).
    rel_weight = 0.90 - imp_weight
    s = 100 * (rel_weight * clear + imp_weight * impressiveness + 0.10 * min(n / RECENT_GAMES, 1.0))
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
                          lineups: Lineups | None = None) -> pd.DataFrame:
    """Over-only batter-strikeout props (2+/3+ K) for high-whiff batters."""
    per_game = _per_game(pa, teams)
    if per_game is None:
        return pd.DataFrame(columns=_RESULT_COLUMNS)
    x = pa.loc[pa["batting_team"].isin(teams)]
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
        support = [f"{avg:.1f} strikeouts per game over last {n}",
                   f"{thr}+ K in {cleared} of {n} games"]
        rows.append(_row(batter_id, name, team, "batter_k", "over", thr,
                         _score(clear, imp, n), _stability(clear, n), avg, clear, support,
                         ["Strikeouts swing with the opposing starter and two-strike counts"],
                         lineups))
    return _frame(rows)


def score_bb_opportunities(pa: pd.DataFrame, teams: list[str], minimum_games: int = MIN_GAMES,
                           lineups: Lineups | None = None) -> pd.DataFrame:
    """Over-only batter-walk props (1+/2+ Walk) for patient hitters."""
    per_game = _per_game(pa, teams)
    if per_game is None:
        return pd.DataFrame(columns=_RESULT_COLUMNS)
    x = pa.loc[pa["batting_team"].isin(teams)]
    rows = []
    for batter_id, g in per_game.groupby("batter_id"):
        recent = g.sort_values("game_date").tail(RECENT_GAMES)["bb"]
        n = len(recent)
        if n < minimum_games:
            continue
        over = _reliable_over(recent, BB_THRESHOLDS, BB_FLOOR)
        if not over:
            continue
        thr, clear, imp = over
        avg = float(recent.mean())
        name, team = _name_team(x, per_game, batter_id)
        cleared = int(round(clear * n))
        support = [f"{avg:.1f} walks per game over last {n}",
                   f"{thr}+ walk in {cleared} of {n} games"]
        rows.append(_row(batter_id, name, team, "batter_bb", "over", thr,
                         _score(clear, imp, n, imp_weight=0.20), _stability(clear, n),
                         avg, clear, support,
                         ["Walks depend on plate discipline and how the pitcher attacks him"],
                         lineups))
    return _frame(rows)


def _row(batter_id, name, team, key, direction, thr, score, stability, avg, clear,
         support, risks, lineups) -> dict:
    score, stability, slot, _posted = lineup_overlay.apply(
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
