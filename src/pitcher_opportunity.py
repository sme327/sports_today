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

from domain.markets import format_market

_REQUIRED = {"pitcher_id", "pitcher_name", "pitching_team", "game_id", "game_date",
             "inning", "is_strikeout", "is_hit"}

K_THRESHOLDS = (4, 5, 6, 7, 8)
HITS_THRESHOLDS = (4, 5, 6, 7, 8)      # hits allowed — over or under
MIN_STARTS = 3
# A rotation turns over every ~5 days; well beyond that per start means the window
# has jumped an absence. Stability (our confidence in the *sample*) takes the hit;
# the opportunity score is left alone until a scoring change can be validated
# against graded results.
_STALE_DAYS_PER_START = 12
_STALE_STABILITY_PENALTY = 25
RECENT_STARTS = 6
MIN_START_BF = 10                      # batters faced to count as a start (excludes openers)

_RESULT_COLUMNS = ["recent_line", "pitcher_id", "player", "team", "market", "threshold", "kind",
                   "direction", "opportunity_score", "stability_score", "starts",
                   "recent_avg", "recent_hit_rate", "support", "risks"]


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


# Ledger-refit (sp-v2): recommended SP *overs* badly underperformed (hits-allowed
# overs hit only 20% off a 60% recent clear rate — the stat is too variance-driven —
# and K overs regressed to ~43%), while *unders* converted 57–61%. So overs are
# penalized in the direction choice: an over must be clearly stronger than the under
# to be served, strongly so for hits allowed.
_OVER_PENALTY = {"sp_k": 0.70, "sp_hits": 0.45}

# How often a start actually clears each bar, as (P(value <= t), P(value >= t)).
# Measured over 14,188 starts in the 2020-24 Big Data Ball box-score history
# (`mlb_box_player_games`). These are league base rates, not this pitcher's — they say how
# *hard* a bar is, which is what "impressive" should mean.
#
# Why this exists: impressiveness used to be linear in the threshold's **value**
# (`1 - (t-lo)/span`), so an under at `<=4` scored 1.00 while happening 46% of the time and
# `<=8` scored 0.00 while happening 95% of the time. Because a direction's value is
# clear-rate x impressiveness, the hardest bar won the argmax on impressiveness alone. The
# ledger shows the damage: the scorer picked `<=4` 96 times (converting 37.5%) over `<=6`
# 32 times (90.6%) — the hardest bar most often, and it converted worst.
#
# Backtested on 45,020 leakage-safe simulated starts (prior 6 starts only), scored as
# **lift over base rate** rather than raw conversion. Rarity beat linear in every score
# band for both markets: sp_k 70-79 went +0.019 -> +0.130 and 90+ went +0.184 -> +0.346;
# sp_hits 70-79 went **-0.037 -> +0.047**, i.e. from serving props worse than the base rate
# to serving useful ones. The over-penalties above were left untouched: once impressiveness
# is right they move lift by ~0.01, so the sp-v2 decision did not need reversing.
_CLEAR_RATES: dict[str, dict[int, tuple[float, float]]] = {
    "sp_k": {
        4: (0.492, 0.662), 5: (0.637, 0.508), 6: (0.763, 0.363),
        7: (0.854, 0.237), 8: (0.917, 0.146),
    },
    "sp_hits": {
        4: (0.464, 0.710), 5: (0.633, 0.536), 6: (0.779, 0.367),
        7: (0.882, 0.221), 8: (0.947, 0.118),
    },
}


def _impressiveness(stat: str, threshold: int, direction: str, thresholds) -> float:
    """How rare it is to clear this bar — 1 minus how often it happens.

    Falls back to the old linear-in-value shape when a threshold has no measured rate, so
    a new bar cannot silently score as maximally impressive.
    """
    rates = _CLEAR_RATES.get(stat, {}).get(threshold)
    if rates is not None:
        under_rate, over_rate = rates
        return 1.0 - (over_rate if direction == "over" else under_rate)
    lo, hi = min(thresholds), max(thresholds)
    # Clamped: a threshold outside the configured range would otherwise produce a wildly
    # out-of-scale value (a bar of 99 against 4-8 gave -22.75) and poison the argmax.
    norm = min(1.0, max(0.0, (threshold - lo) / ((hi - lo) or 1)))
    return norm if direction == "over" else 1 - norm


def _best_direction(values: pd.Series, thresholds, over_penalty: float = 1.0,
                    stat: str = "") -> dict:
    """The stronger of an over vs. an under opportunity for a stat.

    Each threshold has an "impressiveness" — how *rare* clearing it actually is, from
    ``_CLEAR_RATES``. A direction's value = clear-rate × impressiveness (× ``over_penalty``
    for overs, which the ledger shows are unreliable). A dominant starter still surfaces a
    strong over; otherwise the under wins. Never a trivial bar: anything the league clears
    (or misses) almost always has impressiveness near zero and cannot win."""
    lo, hi = min(thresholds), max(thresholds)
    n = len(values)
    avg = float(values.mean())

    over = [(float((values >= t).mean()), t, _impressiveness(stat, t, "over", thresholds))
            for t in thresholds]
    over = [x for x in over if x[2] > 0]
    o_rate, o_thr, o_imp = max(over, key=lambda x: x[0] * x[2], default=(0.0, hi, 0.0))
    under = [(float((values <= t).mean()), t, _impressiveness(stat, t, "under", thresholds))
             for t in thresholds]
    under = [x for x in under if x[2] > 0]
    u_rate, u_thr, u_imp = max(under, key=lambda x: x[0] * x[2], default=(0.0, lo, 0.0))

    if o_rate * o_imp * over_penalty >= u_rate * u_imp:
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
        span = _window_span_days(recent["game_date"])
        rows.append(_stat_prop(pid, name, team, "sp_k", "Strikeouts", "K",
                               recent["k"], K_THRESHOLDS, span))
        rows.append(_stat_prop(pid, name, team, "sp_hits", "Hits Allowed", "hits",
                               recent["hits"], HITS_THRESHOLDS, span))
    result = pd.DataFrame(rows, columns=_RESULT_COLUMNS)
    if result.empty:
        return result
    return result.sort_values(["opportunity_score", "stability_score"],
                              ascending=False).reset_index(drop=True)


def _window_span_days(dates) -> int | None:
    """Calendar days covered by the starts in the window, or None if undatable."""
    try:
        parsed = pd.to_datetime(pd.Series(list(dates)), errors="coerce").dropna()
    except Exception:
        return None
    if len(parsed) < 2:
        return None
    return int((parsed.max() - parsed.min()).days)


def _is_stale_window(span_days: int | None, starts: int) -> bool:
    """Whether these starts are too spread out to be called recent form.

    A rotation turns over every five days, so N starts should span roughly 5N days.
    Well past that means the window has jumped a gap — an injury, a demotion, a
    role change — and the numbers on either side describe different pitchers.
    Observed live: a pitcher's "last 4 starts" spanned 122 days across a three-month
    absence, including the outing he left early, and scored 95.
    """
    return bool(span_days is not None and starts >= 2
                and span_days > _STALE_DAYS_PER_START * starts)


def _stat_prop(pid, name, team, kind, stat_label, unit, values, thresholds,
               span_days: int | None = None) -> dict:
    """``values`` arrives newest-first; the line is reversed so it reads as time."""
    d = _best_direction(values, thresholds, _OVER_PENALTY.get(kind, 1.0), kind)
    thr, n, avg, hit = d["threshold"], d["n"], d["avg"], d["hit_rate"]
    cleared = int(round(hit * n))
    market = format_market(kind, thr, d["direction"])   # one label source of truth
    if d["direction"] == "over":
        support = [f"{avg:.1f} {unit} per start over last {n}",
                   f"Reached {thr}+ in {cleared} of {n} starts"]
    else:
        support = [f"{avg:.1f} {unit} per start over last {n}",
                   f"Held to {thr} or fewer in {cleared} of {n} starts"]
    risks = []
    if _is_stale_window(span_days, n):
        # Named first: it changes how everything above should be read.
        risks.append(f"These {n} starts span {span_days} days — not a continuous "
                     f"recent run, so this is not current form")
    risks.append("Strikeout totals swing with the opposing lineup and pitch count"
                 if kind == "sp_k" else
                 "Hits allowed depends heavily on opponent and batted-ball luck")
    stability = _stability(hit, n)
    if _is_stale_window(span_days, n):
        stability = max(0, stability - _STALE_STABILITY_PENALTY)
    return _row(pid, name, team, market, thr, kind, d["direction"], d["score"],
                stability, n, avg, hit, support=support, risks=risks,
                recent_line=[float(v) for v in values][::-1])


def _row(pid, name, team, market, threshold, kind, direction, score, stability, starts,
         avg, hit_rate, *, support, risks, recent_line=None) -> dict:
    return {"pitcher_id": str(pid), "player": name, "team": team, "market": market,
            "recent_line": list(recent_line or []),
            "threshold": threshold, "kind": kind, "direction": direction,
            "opportunity_score": score, "stability_score": stability, "starts": starts,
            "recent_avg": round(avg, 2), "recent_hit_rate": round(hit_rate, 3),
            "support": support[:3], "risks": risks[:2]}
