from __future__ import annotations

import pandas as pd

from src import lineup_overlay
from src.availability import InjuryReport
from src.mlb_lineups import Lineups


_REQUIRED_COLUMNS = {
    "batting_team", "batter_id", "batter_name", "game_date", "game_id",
    "pa_number", "is_hit", "reached_base", "is_strikeout", "pitch_count_pa",
}

_RESULT_COLUMNS = [
    "batter_id", "player", "team", "market", "opportunity_score",
    "stability_score", "last_25_hit_rate", "last_50_hit_rate",
    "pa_per_game", "k_rate", "lineup_slot", "support", "risks",
]

# Shrinkage: pull a batter's noisy recent per-PA hit rate toward the league mean before
# estimating the 1+ hit chance, so hot streaks don't rocket to a saturated, mean-reverting
# top. v3 introduced this at 0.70; **v5 cut it to 0.25** after measuring which inputs
# actually predict the outcome, on 28,000 leakage-safe batter-games from our own feed:
#
#     corr(plate appearances per game, got a hit) = +0.1296
#     corr(recent per-PA hit rate,     got a hit) = +0.0539
#     corr(recent strikeout rate,      got a hit) = -0.0494
#
# **How many chances a batter gets predicts a 1+ hit more than twice as well as how well
# he has been hitting.** So the recent rate deserves far less weight than v3 gave it.
# Validated out of sample (fit on the first half of the season, tested on the second):
# test correlation +0.1127 -> +0.1314, served conversion 0.6304 -> 0.6417, top-20%
# conversion 0.6419 -> 0.6556 and its spread over the bottom 20% +0.1613 -> +0.1879.
# The trend is monotonic down to ~0.10; 0.25 is near-optimal and still lets recorded form
# matter, which keeps the score explainable against the evidence shown beside it.
#
# _LEAGUE_HIT_RATE is **not** the true league per-PA hit rate — that is 0.2092 in our own
# data (0.25 is nearer a batting average, hits per official at-bat, which is 0.2347).
# It is left as-is deliberately: shrinkage is linear, so the constant sets the score's
# zero point rather than its ordering, and it is entangled with the scale below. Corrected
# in isolation it changes nothing measurable (re-scaled test correlation +0.1137 vs
# +0.1119). Do not "fix" it without re-tuning _SCORE_OFFSET/_SCORE_SPAN together.
_LEAGUE_HIT_RATE = 0.25
_HIT_SHRINK = 0.25

# Maps the estimated 1+ hit chance onto 0-100. Re-tuned with the v5 shrinkage to preserve
# how much of the slate clears the curation floor (served 70+: 18.7% before, 19.3% after) —
# heavier shrinkage compresses the estimate, so the old (0.45, 0.37) pair would have
# quietly halved the served population.
_SCORE_OFFSET = 0.550
_SCORE_SPAN = 0.225

# Per-PA hit rate over the short window at or below which "cooled" understates it.
# A league-average hitter sits near .250 per PA; half of that over 25 PA is a real
# slump, not noise, and deserves to be named with its raw count.
_COLD_PA_RATE = 0.12

# --- Opposing-starter context -------------------------------------------------
# Who is pitching is the largest single input this market was missing. Across 261
# starters with >=200 batters faced the spread is .167 to .238 hits allowed per
# batter (0.80x to 1.14x league), which moves P(1+ hit) by 10-14 points — wider
# than the scorer's entire graded discrimination. For now this is shown as
# evidence only; folding it into the score is a version bump that needs ledger
# validation first.
_PITCHER_SHRINK_BF = 200   # regress a pitcher's rate toward league over this many BF
_PITCHER_MIN_BF = 100      # below this we say nothing rather than guess
_HITTABLE = 1.10           # allows hits >=10% above league -> favourable for the batter
_STINGY = 0.90             # >=10% below league -> a real headwind


def opposing_starter_note(pa: pd.DataFrame, pitcher_id: str | None) -> tuple[str, str] | None:
    """``(kind, sentence)`` describing tonight's starter, or None when unknown.

    ``kind`` is "good" when the matchup favours the batter and "risk" when it does
    not. The rate is regressed toward league average by batters faced, so a pitcher
    with two starts on record does not swing the wording; below ``_PITCHER_MIN_BF``
    nothing is claimed at all.
    """
    if not pitcher_id or pa.empty or "pitcher_id" not in pa.columns:
        return None
    own = pa.loc[pa["pitcher_id"].astype(str) == str(pitcher_id)]
    bf = len(own)
    if bf < _PITCHER_MIN_BF:
        return None
    league = float(pa["is_hit"].mean())
    if not league:
        return None
    raw = float(own["is_hit"].mean())
    shrunk = (raw * bf + league * _PITCHER_SHRINK_BF) / (bf + _PITCHER_SHRINK_BF)
    ratio = shrunk / league
    name = str(own["pitcher_name"].iloc[-1])
    pct = abs(round((ratio - 1) * 100))
    if ratio >= _HITTABLE:
        return ("good", f"Faces {name}, who allows hits {pct}% above league average")
    if ratio <= _STINGY:
        return ("risk", f"Faces {name}, who allows hits {pct}% below league average")
    return None


def score_hit_opportunities(pa: pd.DataFrame, teams: list[str], minimum_pa: int = 30,
                            lineups: Lineups | None = None,
                            opposing_starters: dict[str, str] | None = None,
                            availability: InjuryReport | None = None) -> pd.DataFrame:
    """``opposing_starters`` maps a batting-team name to the id of the pitcher it
    faces tonight. Used for evidence only — the score is unchanged.

    ``availability`` drops batters who cannot play (injured list, optioned). The
    lineup overlay already caps them once lineups are posted, but that is late in the
    day; before then they score normally, and each one is written into the ledger only
    to void."""
    # Guard: empty input or missing columns yields an empty result, never a crash.
    if pa.empty or not _REQUIRED_COLUMNS.issubset(pa.columns) or not teams:
        return pd.DataFrame(columns=_RESULT_COLUMNS)
    x = pa.loc[pa["batting_team"].isin(teams)].sort_values(["game_date", "game_id", "pa_number"])
    rows = []
    unavailable = (availability.out if availability else {})
    for batter_id, all_pa in x.groupby("batter_id"):
        if str(int(batter_id)) in unavailable:
            continue                    # not on the active roster tonight
        recent = all_pa.tail(50)
        short = all_pa.tail(25)
        if len(recent) < minimum_pa:
            continue
        games = recent["game_id"].nunique()
        hit_rate = recent["is_hit"].mean()
        short_hit_rate = short["is_hit"].mean()
        reach_rate = recent["reached_base"].mean()
        k_rate = recent["is_strikeout"].mean()
        pitches = recent["pitch_count_pa"].mean()
        pa_per_game = len(recent) / max(games, 1)

        # The estimated chance of a 1+ hit — 1-(1-p)^PA, where p is the shrunk recent
        # per-PA hit rate and PA the expected at-bats — rescaled to a 0-100 ranking signal.
        # Shrinkage exists because a 50-PA rate is a noisy talent estimate that regresses:
        # unshrunk, the top saturated (picks tied at 100) and *inverted*. v5 shrinks much
        # harder than v3 did, because plate-appearance volume turns out to carry more than
        # twice the signal of recent form (see _HIT_SHRINK). (1+ hit is a hard ~55% event,
        # so this still doesn't discriminate strongly — it ranks honestly, it doesn't
        # manufacture signal.)
        p = min(max(hit_rate, 0.03), 0.60)
        p = _LEAGUE_HIT_RATE + (p - _LEAGUE_HIT_RATE) * _HIT_SHRINK
        exp_pa = max(pa_per_game, 0.5)
        est = 1.0 - (1.0 - p) ** exp_pa
        est -= 0.12 * max(0.0, k_rate - 0.25)      # small penalty for high recent K rate
        score = (est - _SCORE_OFFSET) / _SCORE_SPAN * 100   # ~[0,100]; clamped by the overlay
        stability = max(0, min(round(55 + min(len(recent), 50) * 0.7 - abs(short_hit_rate - hit_rate) * 40), 100))

        support = []
        risks = []
        if short_hit_rate >= hit_rate + 0.04: support.append("Recent contact results are improving")
        if pa_per_game >= 4.2: support.append("Strong recent plate-appearance volume")
        if k_rate <= 0.20: support.append("Low recent strikeout rate")
        if reach_rate >= 0.38: support.append("Consistently reaching base")
        # Negative evidence has to scale with severity. "Recent hit rate has cooled"
        # is fair for a dip, but it was also the only thing said about a batter with
        # one hit in twenty-five plate appearances — a crisis described as a wobble.
        # Below the cold threshold we state the raw count, which cannot be misread.
        short_hits = int(short["is_hit"].sum())
        if short_hit_rate <= _COLD_PA_RATE:
            risks.append(f"Ice cold — {short_hits} hit{'' if short_hits == 1 else 's'} "
                         f"in the last {len(short)} plate appearances")
        elif short_hit_rate < hit_rate - 0.05:
            risks.append("Recent hit rate has cooled")
        if k_rate >= 0.28: risks.append("Elevated recent strikeout rate")
        if pa_per_game < 3.8: risks.append("Recent plate-appearance volume is limited")

        # --- Lineup overlay (today's posted lineup for today's game) -----------
        team_name = recent["batting_team"].iloc[-1]
        score, stability, slot, team_posted = lineup_overlay.apply(
            batter_id, team_name, score, stability, support, risks, lineups)

        # Inserted at the front, not appended: evidence is capped (support[:3],
        # risks[:2]) and this is the only line about *tonight* rather than about the
        # batter's own recent form, so it must not be the one that gets truncated.
        note = opposing_starter_note(pa, (opposing_starters or {}).get(team_name))
        if note:
            (support if note[0] == "good" else risks).insert(0, note[1])

        if not risks:
            if lineups is not None and slot is None and not team_posted:
                risks.append("Lineup not yet posted")     # actionable, keep
            else:
                risks.append("No standout red flags in recent form")

        rows.append({
            "batter_id": int(batter_id),
            "player": recent["batter_name"].iloc[-1],
            "team": team_name,
            "market": "1+ Hit",
            "opportunity_score": score,
            "stability_score": stability,
            "last_25_hit_rate": short_hit_rate,
            "last_50_hit_rate": hit_rate,
            "pa_per_game": pa_per_game,
            "k_rate": k_rate,
            "lineup_slot": slot,
            "support": support[:3],
            "risks": risks[:2],
        })
    result = pd.DataFrame(rows, columns=_RESULT_COLUMNS)
    if result.empty:
        return result
    return result.sort_values(
        ["opportunity_score", "stability_score"],
        ascending=False,
    ).reset_index(drop=True)
