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

from src.reliability import highest_reachable_over

RECENT_GAMES = 10
MIN_GAMES = 4
_FLOOR = 0.55

# stat column → (label noun, thresholds).
_STAT_MARKETS = {
    "passing_yds": ("Pass Yards", (200, 225, 250, 275, 300)),
    "rushing_yds": ("Rush Yards", (40, 50, 60, 75, 100)),
    "receiving_yds": ("Rec Yards", (40, 50, 60, 75)),
    "receiving_rec": ("Receptions", (3, 4, 5, 6, 7)),
    "rushing_att": ("Rush Att", (10, 12, 15, 18, 20)),
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
