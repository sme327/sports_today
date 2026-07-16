"""WNBA (basketball) analytics engine for the matchup page (pure, no Streamlit).

Aggregates per-player game logs to team-game and team-season profiles, computes
league-relative percentiles, recent form, player roles, and recent trends. All
functions operate on a plate-... no — on a player-game-log frame the caller has
already loaded with an `as_of` bound, so leakage prevention lives in the data
layer. The functions are basketball-generic (reusable for a future NBA page);
only the caller supplies WNBA logs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Documented composite weights (identity/role heuristics — not models).
MIN_TEAM_GAMES = 3
TREND_RECENT_GAMES = 5
TREND_BASELINE_MIN = 5          # games before the recent window
TREND_MAGNITUDE = 0.6           # min |z| to call a player trend
ROLE_MIN_GAMES = 8
ROLE_MIN_MPG = 16

_TEAM_NUM = ["points", "field_goals_made", "field_goals_attempted",
             "three_pointers_made", "three_pointers_attempted",
             "free_throws_made", "free_throws_attempted",
             "offensive_rebounds", "defensive_rebounds", "rebounds",
             "assists", "steals", "blocks", "turnovers", "personal_fouls"]


def _pct(s: pd.Series) -> pd.Series:
    return s.rank(pct=True) * 100.0


def _safe(n, d) -> float:
    return float(n / d) if d else 0.0


def team_game_frame(logs: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, team): summed box score + the opponent's box score."""
    d = logs.copy()
    for c in _TEAM_NUM:
        d[c] = pd.to_numeric(d.get(c), errors="coerce")
    d["game_date"] = pd.to_datetime(d["game_date"], utc=True, errors="coerce")
    agg = d.groupby(["game_id", "team_id"], as_index=False).agg(
        team=("team", "first"), team_abbr=("team_abbr", "first"),
        game_date=("game_date", "first"), opponent=("opponent", "first"),
        opponent_id=("opponent_id", "first"), home_away=("home_away", "first"),
        pts=("points", "sum"), fgm=("field_goals_made", "sum"), fga=("field_goals_attempted", "sum"),
        tpm=("three_pointers_made", "sum"), tpa=("three_pointers_attempted", "sum"),
        ftm=("free_throws_made", "sum"), fta=("free_throws_attempted", "sum"),
        oreb=("offensive_rebounds", "sum"), dreb=("defensive_rebounds", "sum"),
        reb=("rebounds", "sum"), ast=("assists", "sum"), stl=("steals", "sum"),
        blk=("blocks", "sum"), tov=("turnovers", "sum"), pf=("personal_fouls", "sum"))
    # Attach the opponent's stats (same game, other team) for defensive context.
    opp = agg[["game_id", "team_id", "pts", "reb", "tpm", "tpa", "fgm", "fga", "tov"]].rename(
        columns={"team_id": "opp_team_id", "pts": "opp_pts", "reb": "opp_reb",
                 "tpm": "opp_tpm", "tpa": "opp_tpa", "fgm": "opp_fgm",
                 "fga": "opp_fga", "tov": "opp_tov"})
    m = agg.merge(opp, on="game_id")
    m = m[m["team_id"] != m["opp_team_id"]].copy()
    m["fg_pct"] = m.apply(lambda r: _safe(r.fgm, r.fga), axis=1)
    m["tp_pct"] = m.apply(lambda r: _safe(r.tpm, r.tpa), axis=1)
    m["pts_for"] = m["pts"]
    m["pts_against"] = m["opp_pts"]
    m["reb_margin"] = m["reb"] - m["opp_reb"]
    m["scoring_total"] = m["pts"] + m["opp_pts"]
    m["win"] = (m["pts"] > m["opp_pts"]).astype(int)
    return m.sort_values(["team_id", "game_date"])


def team_season_table(tg: pd.DataFrame) -> pd.DataFrame:
    """Per-team season profile + league percentiles/ranks."""
    rows = []
    for tid, g in tg.groupby("team_id"):
        n = len(g)
        rows.append({
            "team_id": tid, "team": g["team"].iloc[-1], "team_abbr": g["team_abbr"].iloc[-1],
            "games": n, "wins": int(g["win"].sum()), "losses": int(n - g["win"].sum()),
            "pts_for": g["pts_for"].mean(), "pts_against": g["pts_against"].mean(),
            "net": g["pts_for"].mean() - g["pts_against"].mean(),
            "fg_pct": _safe(g["fgm"].sum(), g["fga"].sum()),
            "tp_pct": _safe(g["tpm"].sum(), g["tpa"].sum()),
            "tpm_pg": g["tpm"].mean(), "tpa_pg": g["tpa"].mean(),
            "tpa_rate": _safe(g["tpa"].sum(), g["fga"].sum()),      # 3PA share of FGA
            "reb_pg": g["reb"].mean(), "oreb_pg": g["oreb"].mean(),
            "reb_margin": g["reb_margin"].mean(),
            "ast_pg": g["ast"].mean(), "tov_pg": g["tov"].mean(),
            "stl_pg": g["stl"].mean(), "blk_pg": g["blk"].mean(),
            "scoring_pace": g["scoring_total"].mean(),
            "opp_tp_pct": _safe(g["opp_tpm"].sum(), g["opp_tpa"].sum()),  # 3PT allowed
            "two_pt_pg": (g["fgm"] - g["tpm"]).mean(),                    # interior makes
        })
    t = pd.DataFrame(rows).set_index("team_id")
    if t.empty:
        return t
    # League-relative percentiles (higher value -> higher pct; invert "bad" ones).
    t["off_pct"] = _pct(t["pts_for"])
    t["def_pct"] = _pct(-t["pts_against"])
    t["three_pct"] = (_pct(t["tpm_pg"]) + _pct(t["tp_pct"])) / 2
    t["pace_pct"] = _pct(t["scoring_pace"])
    t["reb_pct"] = _pct(t["reb_margin"])
    t["ballmove_pct"] = _pct(t["ast_pg"])
    t["security_pct"] = _pct(-t["tov_pg"])
    t["rim_pct"] = _pct(t["blk_pg"])
    t["perimeter_def_pct"] = _pct(-t["opp_tp_pct"])
    t["paint_pct"] = _pct(t["two_pt_pg"])
    return t


def recent_form(tg: pd.DataFrame, team_id, n: int = 5) -> dict:
    """Last-n record, streak, scoring/defense, and home/road records for a team."""
    g = tg[tg["team_id"] == team_id].sort_values("game_date")
    if g.empty:
        return {}
    last = g.tail(n)
    # Current streak from the most recent games.
    streak, streak_kind = 0, None
    for w in reversed(g["win"].tolist()):
        kind = "W" if w else "L"
        if streak_kind is None:
            streak_kind, streak = kind, 1
        elif kind == streak_kind:
            streak += 1
        else:
            break
    home = g[g["home_away"] == "home"]
    road = g[g["home_away"] == "away"]
    dates = g["game_date"].dropna()
    return {
        "last_n": len(last),
        "record": f"{int(last['win'].sum())}-{int(len(last) - last['win'].sum())}",
        "results": tuple("W" if w else "L" for w in last["win"].tolist()),
        "streak": f"{streak_kind}{streak}" if streak_kind else "—",
        "pts_for": float(last["pts_for"].mean()),
        "pts_against": float(last["pts_against"].mean()),
        "home_record": f"{int(home['win'].sum())}-{int(len(home) - home['win'].sum())}",
        "road_record": f"{int(road['win'].sum())}-{int(len(road) - road['win'].sum())}",
        "last_game_date": dates.max() if len(dates) else None,
        "season_record": f"{int(g['win'].sum())}-{int(len(g) - g['win'].sum())}",
    }


def rest_days(tg: pd.DataFrame, team_id, game_date) -> int | None:
    g = tg[tg["team_id"] == team_id]["game_date"].dropna()
    if g.empty or game_date is None:
        return None
    last = g.max()
    gd = pd.to_datetime(game_date, utc=True, errors="coerce")
    if pd.isna(gd) or pd.isna(last):
        return None
    return max(0, (gd.normalize() - last.normalize()).days)


def season_series(tg: pd.DataFrame, away_id, home_id) -> dict:
    """Prior meetings this season between the two teams."""
    g = tg[(tg["team_id"] == away_id) & (tg["opponent_id"] == home_id)].sort_values("game_date")
    if g.empty:
        return {"played": 0}
    aw = int(g["win"].sum())
    return {"played": len(g), "away_wins": aw, "home_wins": len(g) - aw,
            "last": f"{int(g['pts_for'].iloc[-1])}-{int(g['pts_against'].iloc[-1])}"}


# --- Player roles + trends ---------------------------------------------------
def player_season_frame(logs: pd.DataFrame, team_ids: list) -> pd.DataFrame:
    d = logs[logs["team_id"].astype(str).isin([str(t) for t in team_ids])].copy()
    for c in ("minutes", "points", "rebounds", "assists", "steals", "blocks",
              "turnovers", "field_goals_attempted", "three_pointers_made",
              "three_pointers_attempted", "field_goals_made"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce")
    d["game_date"] = pd.to_datetime(d["game_date"], utc=True, errors="coerce")
    rows = []
    for pid, g in d.groupby("player_id"):
        if len(g) < 3:
            continue
        latest = g.sort_values("game_date").iloc[-1]
        n = len(g)
        rows.append({
            "player_id": str(pid), "player_name": latest.get("player_name"),
            "team_id": str(latest.get("team_id")), "team": latest.get("team"),
            "position": latest.get("position"), "jersey": latest.get("jersey"),
            "headshot": latest.get("headshot"), "games": n,
            "mpg": g["minutes"].mean(), "ppg": g["points"].mean(),
            "rpg": g["rebounds"].mean(), "apg": g["assists"].mean(),
            "spg": g["steals"].mean(), "bpg": g["blocks"].mean(),
            "tpm_pg": g["three_pointers_made"].mean(),
            "fg_pct": _safe(g["field_goals_made"].sum(), g["field_goals_attempted"].sum()),
        })
    return pd.DataFrame(rows)


def player_trend_frame(logs: pd.DataFrame, team_ids: list) -> pd.DataFrame:
    """Recent (last-5) vs baseline deltas per player + composite z-score."""
    d = logs[logs["team_id"].astype(str).isin([str(t) for t in team_ids])].copy()
    for c in ("minutes", "points", "rebounds", "assists", "field_goals_made",
              "field_goals_attempted", "three_pointers_made"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce")
    d["game_date"] = pd.to_datetime(d["game_date"], utc=True, errors="coerce")
    recs = []
    for pid, g in d.groupby("player_id"):
        g = g.sort_values("game_date")
        if len(g) < TREND_RECENT_GAMES + TREND_BASELINE_MIN:
            continue
        recent = g.tail(TREND_RECENT_GAMES)
        baseline = g.iloc[:-TREND_RECENT_GAMES]
        if recent["minutes"].mean() < 12:
            continue

        def avg(frame, col):
            return float(frame[col].mean())
        recs.append({
            "player_id": str(pid), "player_name": g["player_name"].iloc[-1],
            "team_id": str(g["team_id"].iloc[-1]), "team": g["team"].iloc[-1],
            "headshot": g["headshot"].iloc[-1], "position": g["position"].iloc[-1],
            "recent_games": len(recent), "baseline_games": len(baseline),
            "d_pts": avg(recent, "points") - avg(baseline, "points"),
            "d_min": avg(recent, "minutes") - avg(baseline, "minutes"),
            "d_reb": avg(recent, "rebounds") - avg(baseline, "rebounds"),
            "d_ast": avg(recent, "assists") - avg(baseline, "assists"),
            "d_tpm": avg(recent, "three_pointers_made") - avg(baseline, "three_pointers_made"),
            "r_pts": avg(recent, "points"), "b_pts": avg(baseline, "points"),
            "r_min": avg(recent, "minutes"), "b_min": avg(baseline, "minutes"),
            "r_reb": avg(recent, "rebounds"), "r_ast": avg(recent, "assists"),
        })
    df = pd.DataFrame(recs)
    if df.empty:
        return df

    def z(col):
        s = df[col]
        sd = s.std(ddof=0)
        return (s - s.mean()) / sd if sd and not np.isnan(sd) else s * 0.0
    df["trend_score"] = (0.4 * z("d_pts") + 0.25 * z("d_min")
                         + 0.2 * z("d_reb") + 0.15 * z("d_ast"))
    return df
