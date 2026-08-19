"""NFL player prop selection — reachable-bar, over-only, by position.

Same discipline as the other sports: offer a prop only on the highest bar a player
actually clears often (``src/reliability.highest_reachable_over``). NFL props are
volume/yards, so a workhorse back surfaces "60+ rush yards", a target hog "5+
receptions", a volume passer "250+ pass yards" — never a bar they rarely reach.

Used for the matchup page's player spotlights (leakage-safe: score on games before
kickoff, then compare to what the player actually did that game — a built-in backtest).
"""

from __future__ import annotations

import pandas as pd

from domain.markets import OVER, format_market
from src.reliability import highest_reachable_over

RECENT_GAMES = 10
MIN_GAMES = 4
_FLOOR = 0.55

# stat column → (label noun, thresholds).
#
# **The rungs are measured, not assumed** (2026-08-19, 78,744 ingested player-games from
# 2023-25). The trailing rate is how often a *candidate* for that market — someone whose
# per-game mean reaches half the lowest bar — actually clears it league-wide. Each ladder
# steps down about 10 points of rarity per rung, which is what makes "the highest bar he
# still clears" a meaningful statement rather than an artefact of round numbers.
#
# Checked for the saturation defect that sank `batter-hit-v3`: only 17 of 268 props sit on
# the top rung and just one clears it ≥80% of the time, so no ladder is too short.
_STAT_MARKETS = {
    #                              200    225    250    275    300
    "passing_yds": ("Pass Yards", (200, 225, 250, 275, 300)),  # .584 .460 .345 .234 .147
    #                              40     50     60     75     100
    "rushing_yds": ("Rush Yards", (40, 50, 60, 75, 100)),      # .471 .366 .282 .177 .083
    #                               40     50     60     75
    "receiving_yds": ("Rec Yards", (40, 50, 60, 75)),          # .420 .318 .237 .154
    #                              3      4      5      6      7
    "receiving_rec": ("Receptions", (3, 4, 5, 6, 7)),          # .523 .359 .235 .148 .089
    #                             10     12     15     18     20
    "rushing_att": ("Rush Att", (10, 12, 15, 18, 20)),         # .503 .400 .253 .152 .096
}
# Each position's primary prop stat.
_POSITION_STAT = {"QB": "passing_yds", "RB": "rushing_yds", "FB": "rushing_yds",
                  "WR": "receiving_yds", "TE": "receiving_yds"}
# Which players count as "key" per team, and the volume bar to qualify.
_KEY_ROLES = [("QB", "passing_att", 15.0, 1), ("RB", "rushing_att", 8.0, 1),
              ("WR/TE", "receiving_tar", 4.0, 2)]


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def best_prop(player_prior: pd.DataFrame, position: str) -> dict | None:
    """The player's strongest reliable prop (primary stat for their position), from
    their recent prior games. ``None`` if too few games or no reachable bar."""
    stat = _POSITION_STAT.get(str(position).upper())
    if stat is None or player_prior.empty or stat not in player_prior.columns:
        return None
    values = _num(player_prior.sort_values("game_date")[stat].tail(RECENT_GAMES)).dropna()
    if len(values) < MIN_GAMES:
        return None
    label, thresholds = _STAT_MARKETS[stat]
    picked = highest_reachable_over(values, thresholds, _FLOOR)
    if picked is None:
        return None
    threshold, clear = picked
    return {"stat": stat, "label": label, "threshold": threshold,
            "clear_rate": round(clear, 3), "avg": round(float(values.mean()), 1),
            "games": int(len(values))}


def _top(df: pd.DataFrame, stat: str, min_avg: float, k: int) -> list[tuple]:
    if df.empty or stat not in df.columns:
        return []
    agg = (df.assign(**{stat: _num(df[stat])}).groupby(["player_id", "player", "position"])[stat]
           .mean().reset_index())
    agg = agg[agg[stat] >= min_avg].sort_values(stat, ascending=False).head(k)
    return list(agg[["player_id", "player", "position"]].itertuples(index=False, name=None))


def key_players(team_prior: pd.DataFrame) -> list[tuple]:
    """A team's key contributors (QB, lead RB, top WR/TE) by recent role, from their
    prior games. Returns [(player_id, player, position), …]."""
    if team_prior.empty:
        return []
    out: list[tuple] = []
    for role, stat, min_avg, k in _KEY_ROLES:
        pool = (team_prior[team_prior["position"].isin(["WR", "TE"])] if role == "WR/TE"
                else team_prior[team_prior["position"] == role])
        out += _top(pool, stat, min_avg, k)
    return out


# --- slate scoring (2026-08-18) -----------------------------------------------------

# Every market a player can be scored in, not just their position's primary one: a
# receiving back is a genuine receptions prop, and a QB who runs is a rushing-attempts
# prop. `best_prop` picks one for a spotlight; the slate wants the whole population.
_SCORED_MARKETS = {
    "nfl_pass_yds": "passing_yds", "nfl_rush_yds": "rushing_yds",
    "nfl_rec_yds": "receiving_yds", "nfl_receptions": "receiving_rec",
    "nfl_rush_att": "rushing_att",
}

_RESULT_COLUMNS = ["player_id", "player", "team", "position", "market_key", "market",
                   "threshold", "opportunity_score", "stability_score", "clear_rate",
                   "recent_avg", "games", "recent_line", "support", "risks"]


def _score(clear_rate: float, games: int, cushion: float) -> int:
    """0-100, comparable to the other sports' scorers.

    Weighted toward the **clear rate** because that is the term the backtest says earns
    its place. Cushion (how far the recent average sits above the bar) and sample are
    supporting: a player averaging 82 yards against a 60-yard bar is safer than one
    averaging 61.

    **Measured 2026-08-19**, leakage-safe — every player-game scored on that player's
    prior games only, then compared against what he actually did. 10,552 scored
    player-games, base rate .542:

        rushing_att +18.6 · receiving_rec +10.6 · receiving_yds +8.8
        passing_yds +6.5 · rushing_yds +5.2          (points of lift over base)

    At the curation floor the served population hits **.650, +10.8 over base** (n=1,081) —
    the same order as MLB `batter_hit`. Bands rise monotonically out of sample (2025 only:
    +7.0 → +10.8 → +12.8 → +17.8), so the top band is *not* the inverted, saturated shape
    that forced `batter-hit-v5`; the 85+ bucket holds 15 props, which decides nothing.

    An earlier note here claimed +32 to +51. That came from comparing each market's raw
    clear rate to its base rate — not a backtest, and not honest. The numbers above are
    what the scorer actually earns.

    Four alternative shapes were tried against this (cushion capped, cushion dropped,
    consistency substituted, cushion × consistency). **The incumbent won on both ship-rule
    terms**, so nothing changed — see the decision log.
    """
    sample = min(games / RECENT_GAMES, 1.0)
    return max(0, min(100, round(100 * (0.62 * clear_rate + 0.23 * min(cushion, 1.0)
                                        + 0.15 * sample))))


def _stability(games: int, clear_rate: float, spread: float,
               stale_share: float = 0.0) -> int:
    """Confidence in the *sample*, not the pick. A steady role scores higher than a
    boom-or-bust one at the same clear rate — week-to-week volume is the thing football
    actually makes predictable.

    ``stale_share`` is the fraction of the window from a previous season. It cuts
    stability rather than the opportunity score, because the pick itself is not wrong —
    our confidence that the sample still describes this player is what weakens.
    """
    base = 40 + min(games, RECENT_GAMES) * 3.5 + clear_rate * 12 - min(spread, 12)
    return max(0, min(99, round(base - stale_share * 20)))


def _prior_season_count(window: pd.DataFrame) -> int:
    """Games in the window from before the window's newest season."""
    if "season" not in window.columns or window.empty:
        return 0
    seasons = pd.to_numeric(window["season"], errors="coerce").dropna()
    if seasons.empty:
        return 0
    return int((seasons < seasons.max()).sum())


def score_nfl_opportunities(player_prior: pd.DataFrame, teams=None,
                            min_games: int = MIN_GAMES) -> pd.DataFrame:
    """Rank every reachable prop across a population of players.

    ``player_prior`` must already be bounded by the caller (leakage-safe: games strictly
    before the slate date). ``teams`` limits to the slate; ``None`` scores everyone.
    """
    if player_prior.empty or "player_id" not in player_prior.columns:
        return pd.DataFrame(columns=_RESULT_COLUMNS)
    frame = player_prior.sort_values("game_date")
    # **A player is one player, not one player per team.** Identity — team, position, the
    # name we print — comes from his most recent game; his *history* is every game he has
    # played. Keying the groups on team instead split a traded player into per-team
    # fragments, which cost 459 players their track record at week 3 of 2025 (Aaron
    # Rodgers: 20 games played, 2 under his current team, so no prop at all) and hid the
    # prior-season disclosure from exactly the players it exists for.
    current = frame.groupby("player_id", dropna=False).tail(1).set_index("player_id")
    if teams:
        wanted = {str(t) for t in teams if t}
        keep = current.index[current["team"].astype(str).isin(wanted)]
        frame = frame[frame["player_id"].isin(set(keep))]
    if frame.empty:
        return pd.DataFrame(columns=_RESULT_COLUMNS)

    rows: list[dict] = []
    for pid, games in frame.groupby("player_id", dropna=False):
        identity = current.loc[pid]
        name, team = identity["player"], identity["team"]
        position = identity["position"]
        recent = games.sort_values("game_date").tail(RECENT_GAMES)
        # How much of this window predates the current season. In week 1 that is all ten
        # games, across an offseason of trades and depth-chart churn. Measured over the
        # ingested seasons, a mostly-prior-season window clears 50.1% against 54.5% for a
        # clean one — consistent across all five markets (-2.5 to -7.2 points).
        #
        # **Disclosed, not excluded.** Dropping prior-season games was tested: it lifts
        # early-season accuracy by 1.0 point while cutting served props 22%, which is a
        # bad trade. So the reader is told, and stability takes the hit.
        stale_games = _prior_season_count(recent)
        for key, stat in _SCORED_MARKETS.items():
            if stat not in recent.columns:
                continue
            values = _num(recent[stat]).dropna()
            if len(values) < min_games:
                continue
            picked = highest_reachable_over(values, _STAT_MARKETS[stat][1], _FLOOR)
            if picked is None:
                continue
            threshold, clear = picked
            avg = float(values.mean())
            stale_share = stale_games / len(values) if len(values) else 0.0
            cushion = (avg - threshold) / threshold if threshold else 0.0
            spread = float(values.std(ddof=0) or 0) / max(threshold, 1) * 10
            cleared = int((values >= threshold).sum())
            rows.append({
                "player_id": str(pid), "player": name, "team": team,
                "position": position, "market_key": key,
                "market": format_market(key, threshold, OVER),
                "threshold": float(threshold),
                "opportunity_score": _score(clear, len(values), max(cushion, 0.0)),
                "stability_score": _stability(len(values), clear, spread, stale_share),
                "clear_rate": round(float(clear), 3),
                "recent_avg": round(avg, 1), "games": int(len(values)),
                # Oldest first, so the row reads left-to-right as time.
                "recent_line": [float(v) for v in values],
                "support": [
                    f"{avg:.0f} per game over the last {len(values)}",
                    f"Cleared {threshold}+ in {cleared} of {len(values)}",
                ],
                "risks": _risks(values, threshold, clear, len(values), stale_games),
            })
    result = pd.DataFrame(rows, columns=_RESULT_COLUMNS)
    if result.empty:
        return result
    return result.sort_values(["opportunity_score", "stability_score"],
                              ascending=False).reset_index(drop=True)


def _risks(values, threshold: float, clear: float, games: int,
           stale_games: int = 0) -> list[str]:
    """Negative evidence, at least as prominent as the supporting kind.

    Football's specific hazard is that a *role* can vanish between weeks — an injury, a
    game script, a committee backfield — in a way a baseball lineup slot does not. So the
    risks name volatility and thin samples rather than form.
    """
    out: list[str] = []
    if stale_games:
        # Named first: it changes how every other line should be read.
        out.append(f"{stale_games} of these {games} games are from last season — "
                   f"before any offseason roster change")
    if games < 6:
        out.append(f"Only {games} games in the window — a role can change week to week")
    recent_three = list(values)[-3:]
    if len(recent_three) == 3 and sum(v >= threshold for v in recent_three) <= 1:
        out.append(f"Cleared {threshold:g}+ in only "
                   f"{sum(v >= threshold for v in recent_three)} of the last 3")
    if float(values.std(ddof=0) or 0) >= threshold * 0.5:
        out.append("Volume has swung widely between games")
    if not out:
        out.append("Usage, not form, is the risk here — a changed role moves this most")
    return out
