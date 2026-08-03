"""Starting-pitcher opportunity scoring: SP strikeouts (over) and SP hits allowed
(under), from the same plate-appearance grain as the batter scorer.

A "start" is a game where the pitcher faced a batter in the first inning (so a
relief cameo never pollutes the line). Thresholds are chosen from the pitcher's
own recent starts — like the WNBA scorer — not from betting lines (we ingest no
odds). Everything is transparent: the score is a documented blend of recent
hit-rate, cushion, and sample. Leakage-safe: ``pa`` must already be ``as_of``
bounded by the caller.
"""

from __future__ import annotations

import pandas as pd

_REQUIRED = {"pitcher_id", "pitcher_name", "pitching_team", "game_id", "game_date",
             "inning", "is_strikeout", "is_hit"}

K_THRESHOLDS = (4, 5, 6, 7, 8)
HITS_THRESHOLDS = (4, 5, 6, 7, 8)      # hits allowed — an under
MIN_STARTS = 3
RECENT_STARTS = 6

_RESULT_COLUMNS = ["pitcher_id", "player", "team", "market", "threshold", "kind",
                   "opportunity_score", "stability_score", "starts", "recent_avg",
                   "recent_hit_rate", "support", "risks"]


def _per_start_lines(pa_pitcher: pd.DataFrame) -> pd.DataFrame:
    """One row per START (min inning == 1) with K's and hits allowed, newest first."""
    lines = []
    for _, grp in pa_pitcher.groupby("game_id"):
        # inning is stored like "1T"/"1B" (number + top/bottom) — take the number.
        innings = pd.to_numeric(grp["inning"].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
        if innings.min() != 1:               # entered after the 1st → not a start
            continue
        lines.append({
            "game_date": str(grp["game_date"].iloc[0]),
            "k": int(pd.to_numeric(grp["is_strikeout"], errors="coerce").fillna(0).sum()),
            "hits": int(pd.to_numeric(grp["is_hit"], errors="coerce").fillna(0).sum()),
        })
    if not lines:
        return pd.DataFrame(columns=["game_date", "k", "hits"])
    return pd.DataFrame(lines).sort_values("game_date", ascending=False).reset_index(drop=True)


def _choose_over(avg: float, thresholds) -> int:
    """Highest threshold the pitcher usually clears (≤ avg); else the lowest."""
    eligible = [t for t in thresholds if t <= avg]
    return max(eligible) if eligible else min(thresholds)


def _choose_under(avg: float, thresholds) -> int:
    """Lowest threshold the pitcher usually stays under (≥ avg); else the highest."""
    eligible = [t for t in thresholds if t >= avg]
    return min(eligible) if eligible else max(thresholds)


def _score(hit_rate: float, cushion: float, starts: int) -> int:
    """0–100, comparable to the batter/WNBA scorers: mostly the recent clear-rate,
    plus a cushion bonus and a small sample bonus."""
    s = 100 * (0.62 * hit_rate + 0.23 * min(cushion / 2.0, 1.0)
               + 0.15 * min(starts / RECENT_STARTS, 1.0))
    return max(0, min(round(s), 100))


def _stability(hit_rate: float, starts: int) -> int:
    return max(0, min(round(45 + starts * 6 + hit_rate * 15), 100))


def score_pitcher_opportunities(pa: pd.DataFrame, pitcher_ids,
                                minimum_starts: int = MIN_STARTS) -> pd.DataFrame:
    """Score SP strikeout + SP hits-allowed props for the given probable starters.

    ``pitcher_ids`` are the resolved ids of the slate's probable starters. Name and
    team are read from ``pa``. Empty/invalid input yields an empty frame."""
    if pa.empty or not _REQUIRED.issubset(pa.columns) or not list(pitcher_ids):
        return pd.DataFrame(columns=_RESULT_COLUMNS)
    wanted = {str(p) for p in pitcher_ids if p is not None}
    x = pa[pa["pitcher_id"].astype(str).isin(wanted)]
    rows = []
    for pid, grp in x.groupby(pa["pitcher_id"].astype(str)):
        lines = _per_start_lines(grp)
        if len(lines) < minimum_starts:
            continue
        recent = lines.head(RECENT_STARTS)
        n = len(recent)
        name = str(grp["pitcher_name"].iloc[-1])
        team = str(grp["pitching_team"].iloc[-1])

        # --- SP strikeouts (over) ---
        k_avg = float(recent["k"].mean())
        k_thr = _choose_over(k_avg, K_THRESHOLDS)
        k_hit = float((recent["k"] >= k_thr).mean())
        rows.append(_row(pid, name, team, f"{k_thr}+ Strikeouts (SP)", k_thr, "sp_k",
                         _score(k_hit, k_avg - k_thr, n), _stability(k_hit, n), n, k_avg, k_hit,
                         support=[f"{k_avg:.1f} K per start over last {n}",
                                  f"Reached {k_thr}+ K in {int(round(k_hit * n))} of {n} starts"],
                         risks=["Strikeout totals swing with the opposing lineup and pitch count"]))

        # --- SP hits allowed (under) ---
        h_avg = float(recent["hits"].mean())
        h_thr = _choose_under(h_avg, HITS_THRESHOLDS)
        h_hit = float((recent["hits"] <= h_thr).mean())
        rows.append(_row(pid, name, team, f"≤ {h_thr} Hits Allowed (SP)", h_thr, "sp_hits",
                         _score(h_hit, h_thr - h_avg, n), _stability(h_hit, n), n, h_avg, h_hit,
                         support=[f"Allowed {h_avg:.1f} hits per start over last {n}",
                                  f"Held to ≤{h_thr} in {int(round(h_hit * n))} of {n} starts"],
                         risks=["Hits allowed depends heavily on opponent and batted-ball luck"]))
    result = pd.DataFrame(rows, columns=_RESULT_COLUMNS)
    if result.empty:
        return result
    return result.sort_values(["opportunity_score", "stability_score"],
                              ascending=False).reset_index(drop=True)


def _row(pid, name, team, market, threshold, kind, score, stability, starts,
         avg, hit_rate, *, support, risks) -> dict:
    return {"pitcher_id": str(pid), "player": name, "team": team, "market": market,
            "threshold": threshold, "kind": kind, "opportunity_score": score,
            "stability_score": stability, "starts": starts, "recent_avg": round(avg, 2),
            "recent_hit_rate": round(hit_rate, 3), "support": support[:3], "risks": risks[:2]}
