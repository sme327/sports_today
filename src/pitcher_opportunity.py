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
HITS_THRESHOLDS = (4, 5, 6, 7, 8)      # hits allowed — over or under
MIN_STARTS = 3
RECENT_STARTS = 6
MIN_START_BF = 10                      # batters faced to count as a start (excludes openers)

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
        if len(grp) < MIN_START_BF:           # faced too few batters → an opener, not a start
            continue
        lines.append({
            "game_date": str(grp["game_date"].iloc[0]),
            "k": int(pd.to_numeric(grp["is_strikeout"], errors="coerce").fillna(0).sum()),
            "hits": int(pd.to_numeric(grp["is_hit"], errors="coerce").fillna(0).sum()),
        })
    if not lines:
        return pd.DataFrame(columns=["game_date", "k", "hits"])
    return pd.DataFrame(lines).sort_values("game_date", ascending=False).reset_index(drop=True)


def _score(hit_rate: float, impressiveness: float, starts: int) -> int:
    """0–100, comparable to the batter/WNBA scorers: mostly the recent clear-rate,
    weighted by how *meaningful* the threshold is (a high bar reliably exceeded, or
    a low bar reliably stayed under — not a trivial extreme), plus a sample bonus."""
    s = 100 * (0.60 * hit_rate + 0.25 * impressiveness
               + 0.15 * min(starts / RECENT_STARTS, 1.0))
    return max(0, min(round(s), 100))


def _stability(hit_rate: float, starts: int) -> int:
    return max(0, min(round(45 + starts * 6 + hit_rate * 15), 100))


def _best_direction(values: pd.Series, thresholds) -> dict:
    """The stronger of an over vs. an under opportunity for a stat.

    Each threshold has an "impressiveness": for an over, a *high* threshold is
    impressive (``norm``); for an under, a *low* threshold is impressive
    (``1-norm``). A direction's value = clear-rate × impressiveness, so a dominant
    starter surfaces as a high-threshold **over** and a stingy one as a low-threshold
    **under** — never as the trivial "≤ max" / "min+" bet. Returns the winner."""
    lo, hi = min(thresholds), max(thresholds)
    span = (hi - lo) or 1
    n = len(values)
    avg = float(values.mean())

    def norm(t):
        return (t - lo) / span

    # Over: exclude the min threshold (impressiveness 0 → trivial).
    over = [(float((values >= t).mean()), t, norm(t)) for t in thresholds if norm(t) > 0]
    o_rate, o_thr, o_imp = max(over, key=lambda x: x[0] * x[2], default=(0.0, hi, 0.0))
    # Under: exclude the max threshold (impressiveness 0 → trivial).
    under = [(float((values <= t).mean()), t, 1 - norm(t)) for t in thresholds if (1 - norm(t)) > 0]
    u_rate, u_thr, u_imp = max(under, key=lambda x: x[0] * x[2], default=(0.0, lo, 0.0))

    if o_rate * o_imp >= u_rate * u_imp:
        return {"direction": "over", "threshold": o_thr, "hit_rate": o_rate,
                "score": _score(o_rate, o_imp, n), "avg": avg, "n": n}
    return {"direction": "under", "threshold": u_thr, "hit_rate": u_rate,
            "score": _score(u_rate, u_imp, n), "avg": avg, "n": n}


def score_pitcher_opportunities(pa: pd.DataFrame, pitcher_ids,
                                minimum_starts: int = MIN_STARTS) -> pd.DataFrame:
    """Score SP strikeout + SP hits-allowed props for the given probable starters,
    each in its stronger direction (over or under).

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
        name = str(grp["pitcher_name"].iloc[-1])
        team = str(grp["pitching_team"].iloc[-1])
        rows.append(_stat_prop(pid, name, team, "sp_k", "Strikeouts", "K",
                               recent["k"], K_THRESHOLDS))
        rows.append(_stat_prop(pid, name, team, "sp_hits", "Hits Allowed", "hits",
                               recent["hits"], HITS_THRESHOLDS))
    result = pd.DataFrame(rows, columns=_RESULT_COLUMNS)
    if result.empty:
        return result
    return result.sort_values(["opportunity_score", "stability_score"],
                              ascending=False).reset_index(drop=True)


def _stat_prop(pid, name, team, kind, stat_label, unit, values, thresholds) -> dict:
    d = _best_direction(values, thresholds)
    thr, n, avg, hit = d["threshold"], d["n"], d["avg"], d["hit_rate"]
    cleared = int(round(hit * n))
    if d["direction"] == "over":
        market = f"{thr}+ {stat_label} (SP)"
        support = [f"{avg:.1f} {unit} per start over last {n}",
                   f"Reached {thr}+ in {cleared} of {n} starts"]
    else:
        market = f"≤ {thr} {stat_label} (SP)"
        support = [f"{avg:.1f} {unit} per start over last {n}",
                   f"Held to ≤{thr} in {cleared} of {n} starts"]
    risk = ("Strikeout totals swing with the opposing lineup and pitch count"
            if kind == "sp_k" else
            "Hits allowed depends heavily on opponent and batted-ball luck")
    return _row(pid, name, team, market, thr, kind, d["score"], _stability(hit, n),
                n, avg, hit, support=support, risks=[risk])


def _row(pid, name, team, market, threshold, kind, score, stability, starts,
         avg, hit_rate, *, support, risks) -> dict:
    return {"pitcher_id": str(pid), "player": name, "team": team, "market": market,
            "threshold": threshold, "kind": kind, "opportunity_score": score,
            "stability_score": stability, "starts": starts, "recent_avg": round(avg, 2),
            "recent_hit_rate": round(hit_rate, 3), "support": support[:3], "risks": risks[:2]}
