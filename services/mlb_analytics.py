"""MLB offensive analytics engine for the game page (pure, no Streamlit).

Every function operates on a plate-appearance frame that the caller has already
loaded with an `as_of` bound, so leakage prevention lives in the data layer and
these functions never reach for "latest" globally.

Composites are transparent, documented heuristics — weighted blends of
league-relative percentiles — not hidden models. Weights are module constants.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# --- Documented composite weights -------------------------------------------
POWER_W = {"tb_per_pa": 1 / 3, "hr_per_pa": 1 / 3, "xbh_rate": 1 / 3}
CONTACT_W = {"hit_rate": 0.5, "k_avoid": 0.3, "reach_rate": 0.2}
DISCIPLINE_W = {"bb_rate": 0.45, "pitches_per_pa": 0.35, "reach_rate": 0.20}
SPEED_W = {"attempts_per_game": 0.5, "sb_success": 0.5}
RISP_W = {"risp_hit_rate": 1 / 3, "risp_reach": 1 / 3, "risp_tb_per_pa": 1 / 3}
# Recent-form blend (owner-specified): stable underlying indicators, not runs.
FORM_W = {"tb_per_pa": 0.35, "reach_rate": 0.25, "hit_rate": 0.15,
          "k_avoid": 0.15, "bb_rate": 0.10}

# Sample thresholds (documented).
RISP_MIN = 50          # below this, RISP is not shown
RISP_FULL = 100        # at/above this, full-confidence RISP
SPEED_MIN_ATTEMPTS = 10
PITCHER_MIN_PA = 100   # minimum PA faced to rank a pitcher's profile
TREND_RECENT_MIN_PA = 15
TREND_BASELINE_MIN_PA = 35
TREND_MAGNITUDE = 0.6  # min |composite z-score| to call a trend heating/cooling
FORM_TREND_POINTS = 5.0  # index-point move to call recent form up/down
RECENT_GAMES = 10


def _rate(numer: pd.Series, denom: float) -> float:
    return float(numer.sum() / denom) if denom else 0.0


def _team_base_metrics(pa: pd.DataFrame) -> pd.DataFrame:
    """Season-to-date (as_of) base offensive metrics per team."""
    rows = []
    for team, g in pa.groupby("batting_team"):
        n = len(g)
        games = int(g["game_id"].nunique())
        sb = float(g["stolen_bases"].fillna(0).sum())
        cs = float(g["caught_stealing"].fillna(0).sum())
        attempts = sb + cs
        risp = g[g["has_risp"] == 1]
        risp_n = len(risp)
        xbh = int(((g["play_type"].isin(["DOUBLE", "TRIPLE"])) | (g["is_home_run"] == 1)).sum())
        rows.append({
            "team": team, "pa": n, "games": games,
            "hit_rate": _rate(g["is_hit"], n),
            "tb_per_pa": _rate(g["total_bases"], n),
            "hr_per_pa": _rate(g["is_home_run"], n),
            "xbh_rate": xbh / n if n else 0.0,
            "bb_rate": _rate(g["is_walk"], n),
            "k_rate": _rate(g["is_strikeout"], n),
            "k_avoid": 1 - _rate(g["is_strikeout"], n),
            "reach_rate": _rate(g["reached_base"], n),
            "pitches_per_pa": float(g["pitch_count_pa"].mean()) if n else 0.0,
            "sb": sb, "cs": cs, "attempts": attempts,
            "sb_success": (sb / attempts) if attempts else np.nan,
            "attempts_per_game": (attempts / games) if games else 0.0,
            "risp_pa": risp_n,
            "risp_hit_rate": _rate(risp["is_hit"], risp_n) if risp_n else np.nan,
            "risp_reach": _rate(risp["reached_base"], risp_n) if risp_n else np.nan,
            "risp_tb_per_pa": _rate(risp["total_bases"], risp_n) if risp_n else np.nan,
        })
    return pd.DataFrame(rows).set_index("team")


def _pct(series: pd.Series) -> pd.Series:
    """League percentile (0-100), higher value → higher percentile."""
    return series.rank(pct=True) * 100.0


def _composite(table: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    out = pd.Series(0.0, index=table.index)
    for col, w in weights.items():
        out = out + _pct(table[col]) * w
    return out


def team_metric_table(pa: pd.DataFrame) -> pd.DataFrame:
    """Per-team base metrics + composite identity scores, ranks, percentiles."""
    t = _team_base_metrics(pa)
    if t.empty:
        return t
    t["power"] = _composite(t, POWER_W)
    t["contact"] = _composite(t, CONTACT_W)
    t["discipline"] = _composite(t, DISCIPLINE_W)
    # Speed: only rank teams with a usable attempt sample.
    speed = pd.Series(np.nan, index=t.index)
    ok = t["attempts"] >= SPEED_MIN_ATTEMPTS
    if ok.any():
        sub = t[ok]
        speed_ok = _pct(sub["attempts_per_game"]) * 0.5 + _pct(sub["sb_success"].fillna(0)) * 0.5
        speed.loc[sub.index] = speed_ok
    t["speed"] = speed
    # RISP: only teams with a usable RISP sample.
    risp = pd.Series(np.nan, index=t.index)
    rok = t["risp_pa"] >= RISP_MIN
    if rok.any():
        sub = t[rok]
        risp.loc[sub.index] = (
            _pct(sub["risp_hit_rate"]) * RISP_W["risp_hit_rate"]
            + _pct(sub["risp_reach"]) * RISP_W["risp_reach"]
            + _pct(sub["risp_tb_per_pa"]) * RISP_W["risp_tb_per_pa"]
        )
    t["risp"] = risp
    for dim in ("power", "contact", "discipline", "speed", "risp"):
        t[f"{dim}_rank"] = t[dim].rank(ascending=False, method="min")
    return t


def _percentile_in(value: float, dist: pd.Series) -> float:
    d = dist.dropna()
    if d.empty or pd.isna(value):
        return 50.0
    return float((d <= value).mean() * 100.0)


@dataclass(frozen=True)
class RecentForm:
    label: str            # "Trending Up" | "Trending Down" | "Holding Steady"
    direction: str        # "up" | "down" | "steady"
    last10_index: float
    baseline_index: float
    evidence: str
    percentile: float     # league percentile of the last-10 index
    rank: int | None


def _window_rates(g: pd.DataFrame) -> dict[str, float]:
    n = len(g)
    if not n:
        return {}
    return {
        "tb_per_pa": _rate(g["total_bases"], n),
        "reach_rate": _rate(g["reached_base"], n),
        "hit_rate": _rate(g["is_hit"], n),
        "k_avoid": 1 - _rate(g["is_strikeout"], n),
        "bb_rate": _rate(g["is_walk"], n),
        "pa": n,
    }


def _form_index(rates: dict[str, float], dists: dict[str, pd.Series]) -> float:
    if not rates:
        return np.nan
    return sum(_percentile_in(rates[m], dists[m]) * w for m, w in FORM_W.items())


def recent_form(pa: pd.DataFrame, team: str, table: pd.DataFrame) -> RecentForm:
    """Composite offensive form over the team's last 10 games vs. its baseline."""
    g = pa[pa["batting_team"] == team]
    game_dates = g.groupby("game_id")["game_date"].max().sort_values(ascending=False)
    last10_ids = list(game_dates.head(RECENT_GAMES).index)
    if not last10_ids:
        return RecentForm("Holding Steady", "steady", np.nan, np.nan,
                          "Not enough recent games to assess form.", 50.0, None)
    cutoff = game_dates.loc[last10_ids].min()
    recent = g[g["game_id"].isin(last10_ids)]
    baseline = g[g["game_date"] < cutoff]
    dists = {m: table[m] for m in FORM_W}
    r_rates, b_rates = _window_rates(recent), _window_rates(baseline)
    last10_index = _form_index(r_rates, dists)
    baseline_index = _form_index(b_rates, dists) if b_rates else last10_index
    # League percentile / rank of the last-10 index across all teams.
    all_last10 = {}
    for tm, tg in pa.groupby("batting_team"):
        tdates = tg.groupby("game_id")["game_date"].max().sort_values(ascending=False)
        ids = list(tdates.head(RECENT_GAMES).index)
        all_last10[tm] = _form_index(_window_rates(tg[tg["game_id"].isin(ids)]), dists)
    idx_series = pd.Series(all_last10)
    percentile = float((idx_series <= last10_index).mean() * 100.0)
    rank = int(idx_series.rank(ascending=False, method="min").get(team, np.nan)) \
        if not idx_series.empty else None
    delta = last10_index - baseline_index
    if delta >= FORM_TREND_POINTS:
        direction, label = "up", "Trending Up"
    elif delta <= -FORM_TREND_POINTS:
        direction, label = "down", "Trending Down"
    else:
        direction, label = "steady", "Holding Steady"
    evidence = _form_evidence(r_rates, b_rates, direction)
    return RecentForm(label, direction, last10_index, baseline_index, evidence, percentile, rank)


def _form_evidence(recent: dict, baseline: dict, direction: str) -> str:
    if not recent or not baseline:
        return "Limited baseline for a reliable recent-form comparison."
    names = {"tb_per_pa": "total bases per PA", "reach_rate": "on-base rate",
             "hit_rate": "hit rate", "k_avoid": "contact rate", "bb_rate": "walk rate"}
    best_m, best_pct = None, 0.0
    for m in FORM_W:
        b = baseline.get(m, 0.0)
        if b:
            change = (recent[m] - b) / b
            if (direction == "up" and change > best_pct) or (direction == "down" and change < best_pct):
                best_m, best_pct = m, change
    if best_m is None:
        return "Recent underlying offense is roughly in line with its season baseline."
    verb = "up" if best_pct > 0 else "down"
    label = names[best_m]
    label = label[:1].upper() + label[1:]
    return (f"{label} is {verb} {abs(best_pct):.0%} over the team's last 10 games "
            "versus its season baseline.")


# --- Player trends ----------------------------------------------------------
def _player_window_stats(g: pd.DataFrame) -> dict[str, float]:
    n = len(g)
    return {
        "pa": n,
        "hit_rate": _rate(g["is_hit"], n),
        "tb_per_pa": _rate(g["total_bases"], n),
        "reach_rate": _rate(g["reached_base"], n),
        "k_rate": _rate(g["is_strikeout"], n),
        "bb_rate": _rate(g["is_walk"], n),
        "hr_per_pa": _rate(g["is_home_run"], n),
        "games": int(g["game_id"].nunique()),
    }


def player_trend_frame(pa: pd.DataFrame, teams: list[str]) -> pd.DataFrame:
    """Per-player recent (last-10 team games) vs baseline deltas + composite z-score."""
    records = []
    for team in teams:
        tg = pa[pa["batting_team"] == team]
        gdates = tg.groupby("game_id")["game_date"].max().sort_values(ascending=False)
        last10 = list(gdates.head(RECENT_GAMES).index)
        if not last10:
            continue
        cutoff = gdates.loc[last10].min()
        for pid, pg in tg.groupby("batter_id"):
            recent = pg[pg["game_id"].isin(last10)]
            baseline = pg[pg["game_date"] < cutoff]
            if len(recent) < TREND_RECENT_MIN_PA or len(baseline) < TREND_BASELINE_MIN_PA:
                continue
            r, b = _player_window_stats(recent), _player_window_stats(baseline)
            recent_sorted = recent.sort_values("game_date")
            hits_by_game = recent_sorted.groupby("game_id")["is_hit"].max()
            records.append({
                "player_id": str(int(pid)), "player_name": pg["batter_name"].iloc[-1],
                "team": team, "recent_pa": r["pa"], "baseline_pa": b["pa"],
                "recent_games": r["games"], "hit_games": int(hits_by_game.sum()),
                "d_hit": r["hit_rate"] - b["hit_rate"],
                "d_tb": r["tb_per_pa"] - b["tb_per_pa"],
                "d_reach": r["reach_rate"] - b["reach_rate"],
                "d_negk": -(r["k_rate"] - b["k_rate"]),
                "d_bb": r["bb_rate"] - b["bb_rate"],
                "d_hr": r["hr_per_pa"] - b["hr_per_pa"],
                "r_hit": r["hit_rate"], "b_hit": b["hit_rate"],
                "r_tb": r["tb_per_pa"], "b_tb": b["tb_per_pa"],
                "r_reach": r["reach_rate"], "b_reach": b["reach_rate"],
                "r_k": r["k_rate"], "b_k": b["k_rate"],
            })
    df = pd.DataFrame(records)
    if df.empty:
        return df

    def z(col: str) -> pd.Series:
        s = df[col]
        sd = s.std(ddof=0)
        return (s - s.mean()) / sd if sd and not np.isnan(sd) else s * 0.0

    df["trend_score"] = (
        0.30 * z("d_tb") + 0.20 * z("d_hit") + 0.20 * z("d_reach")
        + 0.15 * z("d_negk") + 0.10 * z("d_bb") + 0.05 * z("d_hr")
    )
    return df


# --- Pitcher profiles -------------------------------------------------------
def pitcher_league_table(pa: pd.DataFrame) -> pd.DataFrame:
    """Per-pitcher suppression profile for pitchers with a usable sample."""
    rows = []
    for pid, g in pa.groupby("pitcher_id"):
        n = len(g)
        if n < PITCHER_MIN_PA:
            continue
        hand = g["pitcher_hand"].dropna()
        rows.append({
            "pitcher_id": str(int(pid)) if pd.notna(pid) else "",
            "pitcher_name": g["pitcher_name"].iloc[-1],
            "pa_faced": n,
            "k_rate": _rate(g["is_strikeout"], n),
            "bb_rate": _rate(g["is_walk"], n),
            "hit_rate_allowed": _rate(g["is_hit"], n),
            "tb_per_pa_allowed": _rate(g["total_bases"], n),
            "hand": hand.iloc[0] if len(hand) else None,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.set_index("pitcher_id")
    # Suppression percentiles: higher K% = better; lower BB/hit/TB allowed = better.
    df["k_pct"] = _pct(df["k_rate"])
    df["bb_suppress_pct"] = _pct(-df["bb_rate"])
    df["hit_suppress_pct"] = _pct(-df["hit_rate_allowed"])
    df["tb_suppress_pct"] = _pct(-df["tb_per_pa_allowed"])
    return df


def match_pitcher(pa: pd.DataFrame, name: str | None) -> str | None:
    """Match a probable-pitcher name to a stored pitcher_id (exact, then relaxed)."""
    if not name:
        return None
    exact = pa.loc[pa["pitcher_name"] == name, "pitcher_id"].dropna()
    if len(exact):
        return str(int(exact.iloc[0]))
    norm = name.strip().lower()
    cand = pa.assign(_n=pa["pitcher_name"].astype(str).str.strip().str.lower())
    hit = cand.loc[cand["_n"] == norm, "pitcher_id"].dropna()
    return str(int(hit.iloc[0])) if len(hit) else None


def team_vs_hand(pa: pd.DataFrame, team: str, hand: str | None) -> dict | None:
    """Team offensive rate (reach + TB/PA) vs a given pitcher hand, and overall."""
    if hand not in {"L", "R"}:
        return None
    g = pa[pa["batting_team"] == team]
    vs = g[g["pitcher_hand"] == hand]
    if len(vs) < 100:
        return None
    return {
        "hand": hand,
        "reach_rate": _rate(vs["reached_base"], len(vs)),
        "tb_per_pa": _rate(vs["total_bases"], len(vs)),
        "overall_reach": _rate(g["reached_base"], len(g)),
        "overall_tb": _rate(g["total_bases"], len(g)),
        "pa": len(vs),
    }
