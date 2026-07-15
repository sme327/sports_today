from __future__ import annotations

import pandas as pd


_REQUIRED_COLUMNS = {
    "batting_team", "batter_id", "batter_name", "game_date", "game_id",
    "pa_number", "is_hit", "reached_base", "is_strikeout", "pitch_count_pa",
}

_RESULT_COLUMNS = [
    "batter_id", "player", "team", "market", "opportunity_score",
    "stability_score", "last_25_hit_rate", "last_50_hit_rate",
    "pa_per_game", "k_rate", "support", "risks",
]


def score_hit_opportunities(pa: pd.DataFrame, teams: list[str], minimum_pa: int = 30) -> pd.DataFrame:
    # Guard: empty input or missing columns yields an empty result, never a crash.
    if pa.empty or not _REQUIRED_COLUMNS.issubset(pa.columns) or not teams:
        return pd.DataFrame(columns=_RESULT_COLUMNS)
    x = pa.loc[pa["batting_team"].isin(teams)].sort_values(["game_date", "game_id", "pa_number"])
    rows = []
    for batter_id, all_pa in x.groupby("batter_id"):
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

        score = (
            30 * min(hit_rate / 0.28, 1.25)
            + 20 * min(short_hit_rate / 0.30, 1.25)
            + 15 * min(reach_rate / 0.38, 1.25)
            + 15 * min(pa_per_game / 4.4, 1.15)
            + 10 * max(0, 1 - k_rate / 0.30)
            + 10 * min((pitches or 0) / 4.2, 1.15)
        )
        score = max(0, min(round(score), 100))
        stability = max(0, min(round(55 + min(len(recent), 50) * 0.7 - abs(short_hit_rate - hit_rate) * 40), 100))

        support = []
        risks = []
        if short_hit_rate >= hit_rate + 0.04: support.append("Recent contact results are improving")
        if pa_per_game >= 4.2: support.append("Strong recent plate-appearance volume")
        if k_rate <= 0.20: support.append("Low recent strikeout rate")
        if reach_rate >= 0.38: support.append("Consistently reaching base")
        if short_hit_rate < hit_rate - 0.05: risks.append("Recent hit rate has cooled")
        if k_rate >= 0.28: risks.append("Elevated recent strikeout rate")
        if pa_per_game < 3.8: risks.append("Recent plate-appearance volume is limited")
        if not risks: risks.append("Opponent and confirmed lineup context not yet included")

        rows.append({
            "batter_id": int(batter_id),
            "player": recent["batter_name"].iloc[-1],
            "team": recent["batting_team"].iloc[-1],
            "market": "1+ Hit",
            "opportunity_score": score,
            "stability_score": stability,
            "last_25_hit_rate": short_hit_rate,
            "last_50_hit_rate": hit_rate,
            "pa_per_game": pa_per_game,
            "k_rate": k_rate,
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
