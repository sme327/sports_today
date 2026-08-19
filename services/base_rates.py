"""How often each prop's event happens on its own — the number a hit rate is worth judging against.

**Why this exists.** The Performance page compared every market to the app's *overall* hit
rate. That is a comparison between different questions. A batter getting 1+ hit happens
~55% of the time unprompted; a starter allowing 6 or fewer hits happens ~78% of the time;
a starter striking out 8+ happens ~13% of the time. Ranked against one shared average, the
markets with rare events look bad no matter how well they are picked, and the markets with
common events look fine no matter how badly.

This is [Method §1](../docs/engineering/METHOD.md) — *lift over base rate, never raw
conversion* — applied to the surface that actually drives retirement decisions. The project
already refuses this comparison for team records ("win percentage isn't comparable across
sports"); markets had simply never been given the same treatment.

**It changes conclusions.** Measured against the shared average, ``sp_k`` overs and
``sp_hits`` overs look similar (both below it). Against their own base rates one runs
**+24.8** and the other **−8.7**.

**Resolution is delegated, never re-implemented.** ``domain.markets.grade`` decides what
counts as a hit, and this module asks it — including that an under is ``actual <= threshold``
*inclusive*. Writing that comparison out by hand here once produced a base rate that was
wrong in the flattering direction, which is the failure this whole module exists to prevent.

**Populations are stated, not assumed.** A base rate is only honest against the players who
could plausibly have been offered the prop. Pinch hitters with a single plate appearance
would drag the batter base rate down and make our picks look better than they are, so each
market names its population below and the page shows it.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache

import pandas as pd

from domain import markets
from src.config import DB_PATH

# market key → (column in the population frame, human description of who is counted)
_POPULATION_NOTE = {
    "batter_hit": "starting batters, by game",
    "batter_tb": "starting batters, by game",
    "batter_k": "starting batters, by game",
    "batter_bb": "starting batters, by game",
    "sp_k": "starting pitchers, by start",
    "sp_hits": "starting pitchers, by start",
    "wnba_points": "WNBA starters, by game",
    "wnba_rebounds": "WNBA starters, by game",
    "wnba_assists": "WNBA starters, by game",
}
# NFL: candidates are players whose per-game mean reaches half the market's lowest bar,
# matching how src/nfl_opportunity measured its ladders.
_NFL_NOTE = "NFL players who average at least half the lowest bar"


def _conn(db_path=None) -> sqlite3.Connection:
    return sqlite3.connect(db_path or DB_PATH)


def _mlb_batter_games(db_path=None) -> pd.DataFrame:
    """Per batter-game totals for **starters**.

    A starter is one of the first nine distinct batters a team sends up. That is settled
    before the first pitch, which is the whole point: filtering on plate appearances
    instead (``>= 3 PA``) conditions on how the game went. A batter bats a fourth time
    partly *because* his side kept the inning alive, and partly because he already
    reached — so the filter quietly selects for the outcome being measured. It moved the
    1+ hit base rate from .565 to .741 across plausible cutoffs and flipped this market's
    verdict from +4.9 to −4.5, on a choice the reader never sees. Starters, at .607 and a
    mean 4.16 PA, condition on nothing.
    """
    with _conn(db_path) as conn:
        pa = pd.read_sql_query(
            "SELECT game_id, batting_team, batter_id, is_hit, is_strikeout, is_walk, "
            "total_bases FROM plate_appearances ORDER BY game_id, batting_team, rowid",
            conn)
    starters = (pa.drop_duplicates(["game_id", "batting_team", "batter_id"])
                .groupby(["game_id", "batting_team"]).head(9)
                [["game_id", "batting_team", "batter_id"]])
    own = pa.merge(starters, on=["game_id", "batting_team", "batter_id"])
    return own.groupby(["game_id", "batter_id"]).agg(
        hits=("is_hit", "sum"), k=("is_strikeout", "sum"),
        bb=("is_walk", "sum"), tb=("total_bases", "sum"))


def _mlb_starts(db_path=None) -> pd.DataFrame:
    """Per start totals. The starter is whoever pitched the first inning for their side —
    there is no ``is_starting_pitcher`` column, and ``inning`` is text ("1T"/"1B")."""
    with _conn(db_path) as conn:
        pa = pd.read_sql_query(
            "SELECT game_id, pitching_team, pitcher_id, inning, is_hit, is_strikeout "
            "FROM plate_appearances", conn)
    first = pa[pa["inning"].isin(["1T", "1B"])]
    starters = (first.groupby(["game_id", "pitching_team"])["pitcher_id"].first()
                .reset_index().rename(columns={"pitcher_id": "sp"}))
    merged = pa.merge(starters, on=["game_id", "pitching_team"])
    own = merged[merged["pitcher_id"] == merged["sp"]]
    return own.groupby(["game_id", "sp"]).agg(hits=("is_hit", "sum"),
                                              k=("is_strikeout", "sum"))


def _wnba_games(db_path=None) -> pd.DataFrame:
    """Starters only — the log carries a ``started`` flag, which is known before tip-off.
    Filtering on minutes played would condition on the game instead: a player stays on the
    floor partly because she is scoring."""
    with _conn(db_path) as conn:
        d = pd.read_sql_query(
            "SELECT started, points, rebounds, assists FROM wnba_player_game_logs", conn)
    return d[pd.to_numeric(d["started"], errors="coerce") == 1]


def _nfl_games(db_path=None) -> pd.DataFrame:
    cols = ",".join(sorted(set(markets.NFL_STAT_COLUMN.values())))
    with _conn(db_path) as conn:
        return pd.read_sql_query(f"SELECT player_id,{cols} FROM nfl_player_games", conn)


@lru_cache(maxsize=1)
def _values(db_path_key: str) -> dict[str, pd.Series]:
    """Every market's population, as a Series of the stat the market grades on."""
    db = db_path_key or None
    out: dict[str, pd.Series] = {}
    try:
        bat = _mlb_batter_games(db)
        out |= {"batter_hit": bat["hits"], "batter_tb": bat["tb"],
                "batter_k": bat["k"], "batter_bb": bat["bb"]}
        sp = _mlb_starts(db)
        out |= {"sp_k": sp["k"], "sp_hits": sp["hits"]}
    except Exception:
        pass  # MLB workbook absent — those markets simply report no base rate.
    try:
        w = _wnba_games(db)
        out |= {"wnba_points": w["points"], "wnba_rebounds": w["rebounds"],
                "wnba_assists": w["assists"]}
    except Exception:
        pass
    try:
        nfl = _nfl_games(db)
        for key, col in markets.NFL_STAT_COLUMN.items():
            vals = pd.to_numeric(nfl[col], errors="coerce")
            frame = nfl.assign(v=vals).dropna(subset=["v"])
            spec_bars = _nfl_bars(key)
            if spec_bars:
                mean_by = frame.groupby("player_id")["v"].mean()
                cand = set(mean_by[mean_by >= min(spec_bars) * 0.5].index)
                frame = frame[frame["player_id"].isin(cand)]
            out[key] = frame["v"]
    except Exception:
        pass
    return out


def _nfl_bars(key: str) -> tuple:
    from src.nfl_opportunity import _SCORED_MARKETS, _STAT_MARKETS
    stat = _SCORED_MARKETS.get(key)
    return _STAT_MARKETS[stat][1] if stat else ()


@lru_cache(maxsize=512)
def base_rate(market_key: str, threshold, direction: str | None = None,
              db_path=None) -> float | None:
    """How often this exact prop lands on its own, across the market's population.

    ``None`` when the population is unavailable — the caller shows nothing rather than
    inventing a comparison.
    """
    if threshold is None:
        return None
    values = _values(str(db_path or "")).get(market_key)
    if values is None or values.empty:
        return None
    # Grade the distinct values only — they are small integers — so the real resolution
    # rule is used without paying for it per row.
    uniq = pd.unique(values.dropna())
    if not len(uniq):
        return None
    hit = {v: markets.grade(market_key, float(v), threshold, direction) == "hit"
           for v in uniq}
    return float(values.dropna().map(hit).mean())


def population_note(market_key: str) -> str:
    """Who the base rate counts, for the page to show alongside it."""
    if market_key in markets.NFL_STAT_COLUMN:
        return _NFL_NOTE
    return _POPULATION_NOTE.get(market_key, "")


def row_base_rate(row: dict, db_path=None) -> float | None:
    """Base rate for one graded ledger row."""
    return base_rate(row.get("market_key") or row.get("market"), row.get("threshold"),
                     row.get("direction"), db_path=db_path)


def segment_base_rate(rows, db_path=None) -> float | None:
    """The mix-weighted base rate for a set of graded rows.

    A segment can mix markets, bars and directions (grouping by team or player does), so
    its base rate is the mean of its rows' own base rates — the rate you would expect from
    picking this exact mix of props at random.
    """
    rates = [r for r in (row_base_rate(row, db_path) for row in rows) if r is not None]
    return sum(rates) / len(rates) if rates else None
