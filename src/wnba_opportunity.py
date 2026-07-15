from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.config import DB_PATH


MARKETS = {
    "points": {"label": "Points", "thresholds": (10, 15, 20, 25)},
    "rebounds": {"label": "Rebounds", "thresholds": (4, 6, 8, 10)},
    "assists": {"label": "Assists", "thresholds": (3, 5, 7, 9)},
}


def load_logs(db_path: Path = DB_PATH) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(db_path) as conn:
        try:
            return pd.read_sql_query(
                """
                SELECT *
                FROM wnba_player_game_logs
                ORDER BY game_date, game_id
                """,
                conn,
            )
        except Exception:
            return pd.DataFrame()


def _normalize(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _choose_threshold(values: pd.Series, thresholds: tuple[int, ...]) -> int | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if len(clean) < 5:
        return None
    anchor = 0.65 * clean.head(10).mean() + 0.35 * clean.mean()
    eligible = [threshold for threshold in thresholds if threshold <= anchor]
    return max(eligible) if eligible else min(thresholds)


def _hit_rate(values: pd.Series, threshold: float, games: int) -> float:
    clean = pd.to_numeric(values.head(games), errors="coerce").dropna()
    return float((clean >= threshold).mean()) if len(clean) else 0.0


def score_wnba_opportunities(
    logs: pd.DataFrame,
    scheduled_teams: Iterable[str],
    *,
    max_per_player: int = 2,
) -> pd.DataFrame:
    columns = [
        "player_id", "player", "team_id", "team", "team_abbr", "headshot",
        "market", "market_label", "threshold", "display_market",
        "opportunity_score", "stability_score", "minutes_l5", "minutes_l10",
        "average_l5", "average_l10", "hit_rate_l5", "hit_rate_l10",
        "support", "risks",
    ]
    if logs.empty:
        return pd.DataFrame(columns=columns)

    tokens = {_normalize(value) for value in scheduled_teams if value}
    if not tokens:
        return pd.DataFrame(columns=columns)

    data = logs.copy()
    team_tokens = data.get("team_abbr", pd.Series(index=data.index, dtype=object)).map(_normalize)
    team_id_tokens = data.get("team_id", pd.Series(index=data.index, dtype=object)).map(_normalize)
    team_name_tokens = data.get("team", pd.Series(index=data.index, dtype=object)).map(_normalize)
    data = data.loc[
        team_tokens.isin(tokens)
        | team_id_tokens.isin(tokens)
        | team_name_tokens.isin(tokens)
    ].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)

    data["game_date"] = pd.to_datetime(data["game_date"], utc=True, errors="coerce")
    numeric_columns = [
        "minutes", "points", "rebounds", "assists",
        "field_goals_attempted", "three_pointers_attempted",
        "free_throws_attempted", "started",
    ]
    for column in numeric_columns:
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.sort_values(
        ["player_id", "game_date", "game_id"],
        ascending=[True, False, False],
    )

    rows: list[dict] = []
    for player_id, group in data.groupby("player_id", dropna=False):
        group = group.drop_duplicates("game_id")
        if len(group) < 5:
            continue

        latest = group.iloc[0]
        minutes_l5 = float(group["minutes"].head(5).mean())
        minutes_l10 = float(group["minutes"].head(10).mean())
        minutes_sd = float(group["minutes"].head(10).std(ddof=0) or 0)
        if math.isnan(minutes_l5) or minutes_l5 < 16:
            continue

        player_rows: list[dict] = []
        for market, spec in MARKETS.items():
            threshold = _choose_threshold(group[market], spec["thresholds"])
            if threshold is None:
                continue

            avg_l5 = float(group[market].head(5).mean())
            avg_l10 = float(group[market].head(10).mean())
            hit_l5 = _hit_rate(group[market], threshold, 5)
            hit_l10 = _hit_rate(group[market], threshold, 10)

            role_score = min(25, max(0, (minutes_l5 - 14) * 1.25))
            recent_score = 22 * hit_l5
            baseline_score = 18 * hit_l10
            cushion = max(0, avg_l10 - threshold)
            cushion_score = min(15, cushion * (1.1 if market == "points" else 2.5))
            trend_score = max(-5, min(8, (avg_l5 - avg_l10) * 2))

            opportunity = round(
                min(99, max(0, 18 + role_score + recent_score + baseline_score + cushion_score + trend_score))
            )
            stability = round(
                min(
                    99,
                    max(
                        0,
                        40 + min(22, len(group) * .8)
                        + min(20, minutes_l10 * .55)
                        + max(0, 12 - minutes_sd),
                    ),
                )
            )

            support: list[str] = []
            risks: list[str] = []
            if minutes_l5 >= 28:
                support.append(f"{minutes_l5:.1f} minutes per game over the last 5")
            elif minutes_l5 >= 22:
                support.append(f"Usable recent role at {minutes_l5:.1f} minutes")
            if hit_l5 >= .8:
                support.append(f"Cleared {threshold}+ in {round(hit_l5 * 5)}/5")
            elif hit_l10 >= .7:
                support.append(f"Cleared {threshold}+ in {round(hit_l10 * 10)}/10")
            if avg_l5 > avg_l10 + .75:
                support.append("Recent production is above the 10-game baseline")
            if avg_l10 >= threshold * 1.15:
                support.append("10-game average provides threshold cushion")

            if minutes_l5 < 24:
                risks.append("Recent playing time is below 24 minutes")
            if minutes_sd >= 7:
                risks.append("Minutes have been volatile")
            if hit_l10 < .5:
                risks.append("Cleared this threshold in fewer than half of the last 10")
            if avg_l5 < avg_l10 - .75:
                risks.append("Recent production is below the 10-game baseline")
            if not risks:
                risks.append("Injuries, projected starters, and matchup context are not yet included")

            player_rows.append({
                "player_id": str(player_id),
                "player": latest.get("player_name"),
                "team_id": str(latest.get("team_id") or ""),
                "team": latest.get("team"),
                "team_abbr": latest.get("team_abbr"),
                "headshot": latest.get("headshot"),
                "market": market,
                "market_label": spec["label"],
                "threshold": threshold,
                "display_market": f"{threshold}+ {spec['label']}",
                "opportunity_score": opportunity,
                "stability_score": stability,
                "minutes_l5": minutes_l5,
                "minutes_l10": minutes_l10,
                "average_l5": avg_l5,
                "average_l10": avg_l10,
                "hit_rate_l5": hit_l5,
                "hit_rate_l10": hit_l10,
                "support": support,
                "risks": risks,
            })

        player_rows.sort(
            key=lambda row: (row["opportunity_score"], row["stability_score"]),
            reverse=True,
        )
        rows.extend(player_rows[:max_per_player])

    result = pd.DataFrame(rows, columns=columns)
    if result.empty:
        return result
    return result.sort_values(
        ["opportunity_score", "stability_score"],
        ascending=False,
    ).reset_index(drop=True)
