"""Reconcile the MLB box-score market lines, which two feed vintages encode differently.

`mlb_box_team_games` is a faithful copy of what the vendor ships, and what it ships for
odds is awkward in a way that made the columns unusable as-is:

**2020-2022.** The `ODDS` block packs *two different quantities into one column*, split
across the game's two rows — one team's row carries the game **total** (4.5-14.0), the
other carries the favourite's **moneyline** (always negative, -107 to -480). It is not
home/road consistent, so position cannot disambiguate it. Magnitude can, cleanly: over
5,886 games, every single one has exactly one value in each range.

**2023.** A different, richer layout: `closing_moneyline` is per team (both sides priced),
`closing_total` is text carrying the line *and* its juice (`"o7.5 -122"`).

This module turns both into one tidy shape. It **reads and interprets**; it does not
rewrite the ingested table, which stays faithful to the source.

**What we do not have.** For 2020-2022 only the favourite is priced, so the underdog's
moneyline is `None` rather than derived — inferring it would mean inventing a number the
vendor never published. And no MLB season here carries a closing *spread*; baseball's
equivalent is the runline, which ships as text (`"-1.5 (-117)"`).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

from src.config import DB_PATH

# A baseball game total lives in this band; a moneyline is |value| >= 100. The bands do
# not overlap, which is what makes the 2020-22 packing recoverable at all.
_TOTAL_LO, _TOTAL_HI = 4.0, 20.0
_MONEYLINE_MIN = 100.0

# "o7.5 -122" / "u9.5" / "o7.5 even" -> 7.5
_TOTAL_TEXT = re.compile(r"[ou]?\s*(\d+(?:\.\d+)?)")


def _num(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def parse_total(value) -> float | None:
    """The total from either vintage: a bare number, or text with its juice attached."""
    n = _num(value)
    if n is not None:
        return n if _TOTAL_LO <= n <= _TOTAL_HI else None
    m = _TOTAL_TEXT.match(str(value or "").strip().lower())
    if not m:
        return None
    n = float(m.group(1))
    return n if _TOTAL_LO <= n <= _TOTAL_HI else None


def _classify(value) -> tuple[str, float] | None:
    """Which quantity a packed 2020-22 cell holds, by magnitude."""
    n = _num(value)
    if n is None:
        return None
    if abs(n) >= _MONEYLINE_MIN:
        return ("moneyline", n)
    if _TOTAL_LO <= n <= _TOTAL_HI:
        return ("total", n)
    return None


def market_lines(db_path: str | Path = DB_PATH) -> pd.DataFrame:
    """One row per team-game: ``game_id, season, team, venue, total, moneyline, is_favourite``.

    ``total`` is game-level (identical on both rows). ``moneyline`` is that team's price
    where the vintage publishes it — for 2020-2022 that is the favourite only, and the
    underdog is left ``None``.
    """
    empty = pd.DataFrame(columns=["game_id", "season", "team", "venue", "total",
                                  "moneyline", "is_favourite"])
    if not Path(str(db_path)).exists():
        return empty
    try:
        with sqlite3.connect(str(db_path)) as conn:
            df = pd.read_sql_query(
                """SELECT game_id, season, team, venue, closing_odds, closing_total,
                          closing_moneyline FROM mlb_box_team_games""", conn)
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return empty
    if df.empty:
        return empty

    rows = []
    for gid, grp in df.groupby("game_id", sort=False):
        # 2023-style: both columns present and per-team.
        totals = [parse_total(v) for v in grp["closing_total"]]
        mls = [_num(v) for v in grp["closing_moneyline"]]
        total = next((t for t in totals if t is not None), None)
        if total is None or all(m is None for m in mls):
            # 2020-22 style: one packed column, split by magnitude across the two rows.
            packed = [_classify(v) for v in grp["closing_odds"]]
            total = next((v for k, v in (p for p in packed if p) if k == "total"), total)
            mls = [v if (p and p[0] == "moneyline") else None
                   for p, v in ((p, (p[1] if p else None)) for p in packed)]
        priced = [m for m in mls if m is not None]
        best = min(priced) if priced else None
        for (_, row), ml in zip(grp.iterrows(), mls):
            rows.append({
                "game_id": gid, "season": row["season"], "team": row["team"],
                "venue": row["venue"], "total": total, "moneyline": ml,
                "is_favourite": bool(ml is not None and best is not None and ml == best
                                     and ml < 0),
            })
    return pd.DataFrame(rows, columns=empty.columns)


def coverage(db_path: str | Path = DB_PATH) -> pd.DataFrame:
    """Per season: games, and how many carry a usable total / moneyline."""
    m = market_lines(db_path)
    if m.empty:
        return m
    return (m.groupby("season")
             .agg(team_rows=("game_id", "size"),
                  games=("game_id", "nunique"),
                  with_total=("total", lambda s: int(s.notna().sum())),
                  with_moneyline=("moneyline", lambda s: int(s.notna().sum())))
             .reset_index())
