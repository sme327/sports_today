"""NFL analytics — team identity, league-relative context, and head-to-head
battlefields, from the ingested per-game feed.

A team's **defense** is derived by pairing each game with the opponent's offensive
row (same game_id): points/yards a team *allowed* are the opponent's points/yards.
Deterministic and inspectable — every number traces to a recorded game. Frames are
already `as_of`-bounded by the repository, so leakage prevention lives in the reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

# Raw feed column → tidy analytics name (offense, from each team's own row).
_OFFENSE = {
    "final": "points", "yards_total_yards": "yards", "rushing_yds": "rush_yds",
    "passing_yds": "pass_yds", "total_plays": "plays", "first_downs": "first_downs",
    "passing_att": "pass_att", "rushing_rush": "rush_att", "passing_comp": "pass_comp",
    "turnovers_penalties_turnovers": "turnovers", "third_downs_made": "third_made",
    "third_downs_att": "third_att", "sacks_sacked": "sacked", "passing_int": "pass_int",
}
_ID = ["game_id", "game_date", "week", "season_type", "team", "opponent"]


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _safe(n: float, d: float) -> float:
    return float(n) / float(d) if d else 0.0


def _pct(s: pd.Series) -> pd.Series:
    """League percentile rank (0–100); ties averaged. Higher input → higher pct."""
    return (s.rank(pct=True) * 100).round().astype("Int64") if len(s) > 1 else s * 0


def team_game_frame(tg: pd.DataFrame) -> pd.DataFrame:
    """One row per team-game: the team's offense + the opponent's offense as the
    team's **allowed** (defense). Win flag included."""
    if tg.empty:
        return pd.DataFrame()
    base = tg.rename(columns=_OFFENSE)
    cols = [c for c in _ID + list(_OFFENSE.values()) if c in base.columns]
    base = base[cols].copy()
    for c in _OFFENSE.values():
        if c in base.columns:
            base[c] = _num(base[c])
    # Opponent's offense (same game) = this team's allowed. Select first (base already
    # has its own `opponent`), then rename `team` into the join key to avoid a collision.
    allowed = base[["game_id", "team", "points", "yards", "rush_yds",
                    "pass_yds", "turnovers", "plays"]].rename(columns={
        "team": "opponent", "points": "points_allowed", "yards": "yards_allowed",
        "rush_yds": "rush_yds_allowed", "pass_yds": "pass_yds_allowed",
        "turnovers": "takeaways", "plays": "plays_allowed"})
    frame = base.merge(allowed, on=["game_id", "opponent"], how="left")
    frame["win"] = (frame["points"] > frame["points_allowed"]).astype("Int64")
    return frame


def team_season_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-team season profile (offense + defense per game) with league percentiles."""
    if frame.empty:
        return pd.DataFrame()
    rows = []
    for team, g in frame.groupby("team"):
        n = len(g)
        rows.append({
            "team": team, "games": n,
            "wins": int(g["win"].sum()), "losses": int(n - g["win"].sum()),
            "points": g["points"].mean(), "points_allowed": g["points_allowed"].mean(),
            "net_points": g["points"].mean() - g["points_allowed"].mean(),
            "yards": g["yards"].mean(), "yards_allowed": g["yards_allowed"].mean(),
            "rush_yds": g["rush_yds"].mean(), "rush_yds_allowed": g["rush_yds_allowed"].mean(),
            "pass_yds": g["pass_yds"].mean(), "pass_yds_allowed": g["pass_yds_allowed"].mean(),
            "plays": g["plays"].mean(),
            "yards_per_play": _safe(g["yards"].sum(), g["plays"].sum()),
            "pass_rate": _safe(g["pass_att"].sum(), (g["pass_att"] + g["rush_att"]).sum()),
            "third_down_pct": _safe(g["third_made"].sum(), g["third_att"].sum()),
            "turnovers": g["turnovers"].mean(), "takeaways": g["takeaways"].mean(),
            "turnover_margin": (g["takeaways"] - g["turnovers"]).mean(),
        })
    t = pd.DataFrame(rows).set_index("team")
    if len(t) < 2:
        return t
    # League-relative percentiles (invert "bad" metrics so higher pct = better).
    t["off_pct"] = _pct(t["points"])
    t["def_pct"] = _pct(-t["points_allowed"])
    t["rush_off_pct"] = _pct(t["rush_yds"])
    t["rush_def_pct"] = _pct(-t["rush_yds_allowed"])
    t["pass_off_pct"] = _pct(t["pass_yds"])
    t["pass_def_pct"] = _pct(-t["pass_yds_allowed"])
    t["efficiency_pct"] = _pct(t["yards_per_play"])
    t["takeaway_pct"] = _pct(t["turnover_margin"])
    return t


@dataclass(frozen=True)
class Battlefield:
    label: str          # e.g. "Cowboys pass offense vs Eagles pass defense"
    attack: float       # attacking team's per-game production
    defense: float      # defending team's per-game allowance
    edge: str           # which side is favored, in words


def _edge(off_pct, def_pct, attacker: str, defender: str) -> str:
    """Who wins a battlefield, from percentiles (offense good high, defense good high)."""
    gap = (off_pct or 0) - (100 - (def_pct or 0))
    if gap >= 20:
        return f"Edge {attacker}"
    if gap <= -20:
        return f"Edge {defender}"
    return "Even"


def battlefields(table: pd.DataFrame, team_a: str, team_b: str,
                 a_disp: str, b_disp: str) -> tuple[Battlefield, ...]:
    """The decisive matchups: each team's pass/rush offense vs the other's defense."""
    if table.empty or team_a not in table.index or team_b not in table.index:
        return ()
    a, b = table.loc[team_a], table.loc[team_b]
    out: list[Battlefield] = []
    for atk, dfn, atk_disp, dfn_disp in ((a, b, a_disp, b_disp), (b, a, b_disp, a_disp)):
        out.append(Battlefield(
            f"{atk_disp} pass offense vs {dfn_disp} pass defense",
            round(atk["pass_yds"], 1), round(dfn["pass_yds_allowed"], 1),
            _edge(atk.get("pass_off_pct"), dfn.get("pass_def_pct"), atk_disp, dfn_disp)))
        out.append(Battlefield(
            f"{atk_disp} rush offense vs {dfn_disp} rush defense",
            round(atk["rush_yds"], 1), round(dfn["rush_yds_allowed"], 1),
            _edge(atk.get("rush_off_pct"), dfn.get("rush_def_pct"), atk_disp, dfn_disp)))
    return tuple(out)


def rest_days(tg: pd.DataFrame, team: str, game_date: str) -> int | None:
    """Days between ``game_date`` and the team's previous game — the rest/schedule
    spot. ``None`` for a season opener (no prior game)."""
    g = tg[(tg["team"] == team) & (tg["game_date"].astype("string") < game_date)]
    if g.empty:
        return None
    prev = str(g["game_date"].max())
    try:
        return (date.fromisoformat(game_date[:10]) - date.fromisoformat(prev[:10])).days
    except ValueError:
        return None


def player_game_frame(pg: pd.DataFrame, team: str | None = None) -> pd.DataFrame:
    """Tidy per-player game logs (passing/rushing/receiving volume + yards + TDs),
    newest first. Optionally restricted to one team."""
    if pg.empty:
        return pd.DataFrame()
    df = pg.copy()
    if team is not None:
        df = df[df["team"] == team]
    keep = ["game_id", "game_date", "week", "player_id", "player", "position", "team", "opponent",
            "passing_att", "passing_yds", "passing_td", "passing_int",
            "rushing_att", "rushing_yds", "rushing_td",
            "receiving_tar", "receiving_rec", "receiving_yds", "receiving_td"]
    df = df[[c for c in keep if c in df.columns]].copy()
    for c in df.columns:
        if c not in ("game_id", "game_date", "player_id", "player", "position", "team", "opponent"):
            df[c] = _num(df[c])
    return df.sort_values("game_date", ascending=False).reset_index(drop=True)
