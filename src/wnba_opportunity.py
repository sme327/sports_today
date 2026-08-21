from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd

from src import score_scale
from src.config import DB_PATH
from src.espn_injuries import InjuryReport
from src.reliability import highest_reachable_over


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


# v2 (ledger-refit): the old anchor (mean-based) routinely picked a bar the player
# clears in <50% of recent games — those hit only ~18–44%, while the recent clear-rate
# (hit_rate_l10) strongly predicts the outcome across all three markets (corr ~0.4).
# So a prop is only offered on the highest bar the player clears in ≥ MIN_CLEAR of the
# last 10; players who clear none are skipped. Hold-out backtest next-game clear:
# points 37%→64%, rebounds 33%→68%, assists 32%→58%.
MIN_CLEAR = 0.60

# v3 (2026-08-12) established the window weighting, backtested on 3,118 leakage-safe
# player-games: the **10-game** clear rate outweighs the 5-game one in every market
# (+0.159 vs +0.121 points, +0.087 vs +0.053 rebounds, +0.183 vs +0.092 assists), and
# the trend term was dropped as noise (+0.031). v4 keeps that validated 18:22 blend as
# 0.45/0.55 and maps it onto the shared lift scale (src/score_scale) against the bar's
# own base rate, replacing the hand-scaled role/cushion/base-constant mix — the 2026-08-20
# ledger evaluation showed the pure blend serves better props at the top (points +37.4 →
# +50.5 realized top-20% lift, rebounds +55.2 → +63.1) while the role and cushion terms
# carried none of it. Minutes still gate eligibility and feed stability.
_RECENT_BLEND = 0.45     # last-5 clear rate
_BASELINE_BLEND = 0.55   # last-10 clear rate

# How often a WNBA **starter** clears each bar on her own — measured 2026-08-20 from
# `wnba_player_game_logs` (started == 1, known pre-tip; a minutes filter would condition
# on the game). The same populations services/base_rates measures; a test guards these
# constants against that module so they cannot drift.
_BASE_CLEAR = {
    "points": {10: 0.628, 15: 0.385, 20: 0.189, 25: 0.079},
    "rebounds": {4: 0.551, 6: 0.336, 8: 0.186, 10: 0.104},
    "assists": {3: 0.499, 5: 0.238, 7: 0.106, 9: 0.043},
}
# Appearances (not roster rows) needed before a player's form is described at all.
MIN_PLAYED_GAMES = 5


def _choose_threshold(values: pd.Series, thresholds: tuple[int, ...]) -> int | None:
    clean = _played(values)
    if len(clean) < 5:
        return None
    recent = clean.head(10)      # newest-first; the recent clear-rate is the signal
    picked = highest_reachable_over(recent, thresholds, MIN_CLEAR)
    return picked[0] if picked else None   # highest reliably-cleared bar, else skip


def _played(values: pd.Series) -> pd.Series:
    """Only games the player actually appeared in, newest first.

    Dropping DNPs *after* slicing let five rows collapse to one game while still
    being reported as "the last 5" — a single June appearance was presented as a
    five-game sample. Drop first, then take the window.
    """
    return pd.to_numeric(values, errors="coerce").dropna()


def _hit_rate(values: pd.Series, threshold: float, games: int) -> float:
    clean = _played(values).head(games)
    return float((clean >= threshold).mean()) if len(clean) else 0.0


def score_wnba_opportunities(
    logs: pd.DataFrame,
    scheduled_teams: Iterable[str],
    *,
    max_per_player: int = 2,
    injuries: InjuryReport | None = None,
) -> pd.DataFrame:
    """``injuries`` removes players listed OUT and flags anyone questionable.

    Availability outranks form: a player's scoring history says nothing about a game
    she will not appear in. Absent or empty report -> no claim either way, never an
    implied clean bill of health.
    """
    columns = [
        "player_id", "player", "team_id", "team", "team_abbr", "headshot",
        "market", "market_label", "threshold", "display_market",
        "opportunity_score", "score_points", "stability_score", "minutes_l5", "minutes_l10",
        "average_l5", "average_l10", "hit_rate_l5", "hit_rate_l10",
        "support", "risks", "recent_line",
    ]
    if logs.empty:
        return pd.DataFrame(columns=columns)

    tokens = {_normalize(value) for value in scheduled_teams if value}
    if not tokens:
        return pd.DataFrame(columns=columns)

    data = logs.copy()
    data["game_date"] = pd.to_datetime(data["game_date"], utc=True, errors="coerce")
    data = data.sort_values(["game_date", "game_id"], ascending=[False, False])

    # Eligibility is decided per PLAYER by the team of their most recent game, not
    # per row. Filtering rows by team kept a traded player's *old* club rows and
    # scored them for tonight: Kelsey Plum moved Sparks -> Mercury in July and was
    # still being offered in a Sparks game, on her stale Sparks games. A player
    # belongs to exactly one team tonight — whoever they last played for.
    def _team_tokens(frame: pd.DataFrame) -> pd.Series:
        parts = [frame.get(col, pd.Series(index=frame.index, dtype=object)).map(_normalize)
                 for col in ("team_abbr", "team_id", "team")]
        return parts[0].where(parts[0].isin(tokens),
                              parts[1].where(parts[1].isin(tokens), parts[2]))

    newest = data.drop_duplicates("player_id")          # newest row per player
    eligible = set(newest.loc[_team_tokens(newest).isin(tokens), "player_id"])
    # Form comes from every recent game the player has played, including any for a
    # previous club — their scoring form travels with them even when the club does not.
    data = data.loc[data["player_id"].isin(eligible)].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)
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

        # Availability first — everything below describes a player who is playing.
        status = injuries.status_for(player_id) if injuries else None
        if status is not None and status.is_out:
            continue

        latest = group.iloc[0]
        played_minutes = _played(group["minutes"])
        minutes_l5 = float(played_minutes.head(5).mean())
        minutes_l10 = float(played_minutes.head(10).mean())
        minutes_sd = float(played_minutes.head(10).std(ddof=0) or 0)
        if math.isnan(minutes_l5) or minutes_l5 < 16:
            continue

        player_rows: list[dict] = []
        for market, spec in MARKETS.items():
            threshold = _choose_threshold(group[market], spec["thresholds"])
            if threshold is None:
                continue

            played = _played(group[market])
            if len(played) < MIN_PLAYED_GAMES:
                continue          # too few actual appearances to describe form
            avg_l5 = float(played.head(5).mean())
            avg_l10 = float(played.head(10).mean())
            hit_l5 = _hit_rate(group[market], threshold, 5)
            hit_l10 = _hit_rate(group[market], threshold, 10)

            # v4: the validated 5/10-game blend, shrunk toward the bar's own base rate
            # by appearances, scored as estimated lift over that base — the same claim
            # the score makes in every migrated market. A bar with no measured base
            # (a threshold outside the grid) cannot be scored; skip rather than guess.
            base = _BASE_CLEAR.get(market, {}).get(threshold)
            if base is None:
                continue
            blend = _RECENT_BLEND * hit_l5 + _BASELINE_BLEND * hit_l10
            est = score_scale.shrink_toward(base, blend, len(played))
            opportunity = score_scale.unified_score(est, base)
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
            if status is not None and status.is_questionable:
                # First, because it changes how every other line should be read.
                risks.append(status.note)
            if minutes_l5 >= 28:
                support.append(f"{minutes_l5:.1f} minutes per game over the last 5")
            elif minutes_l5 >= 22:
                support.append(f"Usable recent role at {minutes_l5:.1f} minutes")
            # How often she actually clears the bar is the single most important
            # number about a prop, and it must always be visible. It used to appear
            # only when strong (L5 >= .8 / L10 >= .7) or poor (L5 <= .4), so props
            # sitting exactly on the MIN_CLEAR floor — the ones that *barely*
            # qualified — showed nothing at all: 6 of 19 on the slate this was found
            # on, every one of them at .60/.60.
            if hit_l5 >= .8:
                support.append(f"Cleared {threshold}+ in {round(hit_l5 * 5)}/5")
            else:
                support.append(f"Cleared {threshold}+ in {round(hit_l10 * 10)}/10")
            if avg_l5 > avg_l10 + .75:
                support.append("Recent production is above the 10-game baseline")
            if avg_l10 >= threshold * 1.15:
                support.append("10-game average provides threshold cushion")

            if minutes_l5 < 24:
                risks.append("Recent playing time is below 24 minutes")
            if minutes_sd >= 7:
                risks.append("Minutes have been volatile")
            # The last-5 clear rate had no rule at all, so a player who had missed
            # this bar in every one of her last five games drew either a mild
            # "below the 10-game baseline" or — worse — "No standout red flags".
            # State it plainly, and scale the wording to how bad it is.
            # A bar is only offered when cleared in >=60% of the last 10 played
            # games, which makes "cleared none of the last 5" arithmetically
            # impossible — it only ever appeared because DNP rows were shrinking the
            # window. Two-of-five is the genuine low end.
            cleared_l5 = round(hit_l5 * 5)
            if hit_l5 <= .4:
                risks.append(f"Cleared {threshold}+ in only {cleared_l5} of the last 5")
            if hit_l10 < .5:
                risks.append("Cleared this threshold in fewer than half of the last 10")
            if avg_l5 < avg_l10 - .75:
                risks.append("Recent production is below the 10-game baseline")
            if not risks:
                risks.append("No standout red flags in recent form")

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
                "score_points": score_scale.lift_points(est, base),
                "stability_score": stability,
                "minutes_l5": minutes_l5,
                "minutes_l10": minutes_l10,
                "average_l5": avg_l5,
                "average_l10": avg_l10,
                "hit_rate_l5": hit_l5,
                "hit_rate_l10": hit_l10,
                "support": support,
                "risks": risks,
                # The actual games, oldest first. `_played` drops DNPs and returns
                # newest-first, so reverse it: a form line reads left-to-right as time.
                "recent_line": [float(v) for v in played.head(10)][::-1],
            })

        player_rows.sort(
            key=lambda row: (row["score_points"], row["stability_score"]),
            reverse=True,
        )
        rows.extend(player_rows[:max_per_player])

    result = pd.DataFrame(rows, columns=columns)
    if result.empty:
        return result
    return result.sort_values(
        ["score_points", "stability_score"],
        ascending=False,
    ).reset_index(drop=True)
