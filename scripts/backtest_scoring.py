"""Offline backtest for MLB batter-hit scoring changes.

Every refit so far (v2, v3, and the rejected v4) was validated ad hoc and the working
code thrown away. This is that harness, kept.

It recomputes a candidate estimate for every graded ``batter_hit`` snapshot using only
data from **before** that slate, then compares its discrimination against the current
scorer on the same rows and the same outcomes. Discrimination — does a higher number
actually go with a higher hit rate — is the thing to judge, not absolute calibration:
the model over-predicts in absolute terms by design and always has.

    python -m scripts.backtest_scoring

The opposing starter for each historical game is reconstructed from the feed itself
(whoever faced that team in the first inning) rather than the stored ``opposing_sp``,
which only exists from 2026-08-07 onward. That is the actual starter rather than the
pre-game probable — a small optimism worth remembering when reading the output.
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from src.config import DB_PATH

# Imported, not restated: this file once said `HIT_SHRINK = 0.70  # matches
# src/opportunity` while the live scorer had moved to 0.25 — a drifted constant in
# the harness silently backtests a formula nobody ships.
from src.opportunity import _HIT_SHRINK as HIT_SHRINK          # noqa: E402
from src.opportunity import _LEAGUE_HIT_RATE as LEAGUE_HIT_RATE  # noqa: E402

PITCHER_SHRINK_BF = 200
MIN_PA = 30


def load(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    pa = pd.read_sql_query("SELECT * FROM plate_appearances", conn)
    graded = pd.read_sql_query(
        """SELECT snapshot_date AS d, player_id, result
           FROM opportunity_snapshots
           WHERE market_key='batter_hit' AND result IN ('hit','miss')""", conn)
    pa["d"] = pa["game_date"].astype(str).str[:10]
    pa["inn_n"] = pd.to_numeric(pa["inning"].astype(str).str.extract(r"(\d+)")[0],
                                errors="coerce")
    pa["b"] = pa["batter_id"].astype(str)
    pa["p"] = pa["pitcher_id"].astype(str)
    graded["player_id"] = graded["player_id"].astype(str)
    return pa, graded


def lineup_slots(pa: pd.DataFrame) -> pd.DataFrame:
    """Each starter's batting-order slot and PA count per game.

    **`pa_number` is the batter's n-th plate appearance of the game, not a global
    sequence** — every leadoff PA is 1, so sorting by it scrambles the batting order
    (and did, in the 2026-08-20 slot-PA experiment: it produced a slot table with the
    3-hole out-earning leadoff). The true order is the feed's own row order; the first
    nine distinct batters per game+team are slots 1–9. Measured this way the table is
    textbook: 4.64 PA at leadoff declining to 3.57 at ninth, away +0.17 over home.
    """
    pa = pa.reset_index(drop=True)
    firsts = pa.drop_duplicates(["game_id", "batting_team", "b"])[
        ["game_id", "batting_team", "b", "d"]].copy()
    firsts["slot"] = firsts.groupby(["game_id", "batting_team"]).cumcount() + 1
    starters = firsts[firsts["slot"] <= 9]
    n_pa = pa.groupby(["game_id", "batting_team", "b"]).size().rename("n_pa").reset_index()
    return starters.merge(n_pa, on=["game_id", "batting_team", "b"])


def with_opposing_starter(pa: pd.DataFrame, graded: pd.DataFrame) -> pd.DataFrame:
    """Attach the starter each batter faced, derived from the feed."""
    first = pa[pa["inn_n"] == 1]
    starters = (first.sort_values("pa_number").groupby(["d", "batting_team"])["p"]
                .first().reset_index().rename(columns={"p": "opp_sp"}))
    team = pa.groupby(["d", "b"])["batting_team"].last().reset_index()
    team = team.rename(columns={"b": "player_id"})
    out = graded.merge(team, on=["d", "player_id"], how="left")
    return out.merge(starters, on=["d", "batting_team"], how="left")


def log5(batter: float, pitcher: float, league: float) -> float:
    num = batter * pitcher / league
    return num / (num + (1 - batter) * (1 - pitcher) / (1 - league))


def run(db_path=DB_PATH) -> pd.DataFrame:
    """One row per graded prop with the current and candidate estimates."""
    pa, graded = load(db_path)
    graded = with_opposing_starter(pa, graded)
    rows = []
    for slate, sub in graded.groupby("d"):
        hist = pa[pa["d"] < slate]                     # strictly before: no leakage
        if hist.empty:
            continue
        league = hist["is_hit"].mean()
        batters = (hist.groupby("b").tail(50).groupby("b")
                   .agg(hit_rate=("is_hit", "mean"), k_rate=("is_strikeout", "mean"),
                        n=("is_hit", "size"), games=("game_id", "nunique")))
        pitchers = hist.groupby("p").agg(ph=("is_hit", "mean"), bf=("is_hit", "size"))
        started = hist[hist["p"].isin(hist[hist["inn_n"] == 1]["p"])]
        bf_per_start = started.groupby(["p", "game_id"]).size().groupby("p").mean()

        for _, r in sub.iterrows():
            b = batters.reindex([r.player_id]).iloc[0]
            if pd.isna(b.hit_rate) or b.n < MIN_PA:
                continue
            ppg = b.n / max(b.games, 1)
            shrunk = LEAGUE_HIT_RATE + (min(max(b.hit_rate, .03), .60) - LEAGUE_HIT_RATE) * HIT_SHRINK
            k_pen = 0.12 * max(0.0, b.k_rate - 0.25)
            current = 1 - (1 - shrunk) ** max(ppg, .5) - k_pen

            sp = pitchers.reindex([str(r.opp_sp)]).iloc[0]
            if pd.isna(sp.ph) or sp.bf < 100:
                candidate = current
            else:
                p_adj = (sp.ph * sp.bf + league * PITCHER_SHRINK_BF) / (sp.bf + PITCHER_SHRINK_BF)
                vs_sp = log5(shrunk, p_adj, league)
                pa_sp = min(max(bf_per_start.get(str(r.opp_sp), 18) / 9.0, .5), ppg)
                candidate = (1 - (1 - vs_sp) ** pa_sp * (1 - shrunk) ** max(ppg - pa_sp, 0)) - k_pen
            rows.append({"hit": r.result == "hit", "current": current,
                         "candidate": candidate, "slate": slate})
    return pd.DataFrame(rows)


def report(df: pd.DataFrame) -> None:
    base = df["hit"].mean()
    print(f"graded rows: {len(df)}   slates: {df.slate.nunique()}   base rate: {base:.1%}\n")
    for col in ("current", "candidate"):
        q = pd.qcut(df[col], 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")
        t = df.groupby(q, observed=True)["hit"].mean()
        top = df[df[col] >= df[col].quantile(.8)]["hit"].mean()
        print(f"{col:10s} " + "  ".join(f"{i}={v:.1%}" for i, v in t.items()))
        print(f"{'':10s} spread {t.iloc[-1] - t.iloc[0]:+.1%}   "
              f"corr {df[col].corr(df['hit']):+.4f}   top-20% lift {top - base:+.1%}\n")
    print("Ship only if the candidate widens the spread AND lifts the top 20%.")


if __name__ == "__main__":
    report(run())
