"""Grade recorded opportunity snapshots against actual results.

For a past slate date, join each snapshotted prop to what the player actually did
that day and mark it hit / miss / void:

- **MLB** ``1+ Hit`` — from ``plate_appearances`` (hits on the slate date).
- **WNBA** ``N+ Points/Rebounds/Assists`` — from ``wnba_player_game_logs``.

Honesty rules: a player who **did not play** (no plate appearances / no box-score
row, or a WNBA log with zero minutes) is **void**, not a miss — a scratch is not a
wrong pick, and counting it would understate our real hit rate. Grading is
idempotent (only pending rows are touched) and only runs for dates strictly before
today, when results are available. This is the learning ledger — nothing is deleted;
we store the outcome and the actual value forever.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from domain import markets
from src.config import DB_PATH

_SNAP = "opportunity_snapshots"


# WNBA registry key → box-score column.
_WNBA_COL = {"wnba_points": "points", "wnba_rebounds": "rebounds", "wnba_assists": "assists"}


def grade_slate(slate_date: date, *, db_path: Path = DB_PATH, force: bool = False) -> dict:
    """Grade all pending snapshot rows for ``slate_date``. Returns summary counts.

    ``force`` re-grades rows even if already graded (e.g. after a data refresh).
    Never grades today or the future (results aren't in). Safe if tables/rows are
    missing — returns zeroes.
    """
    summary = {"graded": 0, "hit": 0, "miss": 0, "void": 0, "pending": 0}
    if slate_date >= date.today():
        return summary
    token = slate_date.isoformat()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            where = "" if force else "AND (result IS NULL OR result = 'pending')"
            rows = conn.execute(
                f"SELECT rowid, league, player_id, market, market_key, direction, threshold "
                f"FROM {_SNAP} WHERE snapshot_date = ? {where}", (token,)).fetchall()
        except sqlite3.OperationalError:
            return summary
        if not rows:
            return summary

        mlb = _mlb_hits(conn, token)          # {batter_id: total_hits}
        mlb_sp = _mlb_pitcher_lines(conn, token)  # {pitcher_id: {k, hits}} for starters
        wnba = _wnba_lines(conn, token)       # {player_id: {points, rebounds, assists, minutes}}
        graded_at = datetime.now().isoformat(timespec="seconds")

        for r in rows:
            result, actual = _grade_row(r, mlb, mlb_sp, wnba)
            if result is None:               # results genuinely not available yet
                summary["pending"] += 1
                continue
            conn.execute(
                f"UPDATE {_SNAP} SET result = ?, actual_value = ?, graded_at = ? WHERE rowid = ?",
                (result, actual, graded_at, r["rowid"]))
            summary["graded"] += 1
            summary[result] += 1
        conn.commit()
    return summary


def _grade_row(r, mlb: dict, mlb_sp: dict, wnba: dict) -> tuple[str | None, float | None]:
    """Grade one snapshot row via the market registry. Reads the stored
    ``market_key``/``direction`` when present, else resolves them from the legacy
    market text — so old ledger rows grade identically. Void (did-not-play) stays a
    source-specific rule; the hit/miss comparison comes from the registry."""
    key = _row_get(r, "market_key") or None
    direction = _row_get(r, "direction") or None
    if key is None:
        key, direction = markets.resolve(r["league"], r["market"])
    if key is None:
        return None, None                   # unknown market → leave pending

    threshold = r["threshold"]
    pid = str(r["player_id"])

    if key == "batter_hit":
        if pid not in mlb:                  # did not bat that day
            return "void", None
        actual = mlb[pid]
    elif key in ("sp_k", "sp_hits"):
        line = mlb_sp.get(pid)
        if line is None:                    # did not start
            return "void", None
        actual = line["k"] if key == "sp_k" else line["hits"]
    elif key in _WNBA_COL:
        line = wnba.get(pid)
        if line is None or not line.get("minutes"):   # not in box score / did not play
            return "void", None
        actual = line.get(_WNBA_COL[key])
        if actual is None:
            return "void", None
    else:
        return None, None

    return markets.grade(key, actual, threshold, direction), float(actual)


def _row_get(r, col):
    """sqlite3.Row has no .get(); tolerate rows that predate a column."""
    try:
        return r[col]
    except (IndexError, KeyError):
        return None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _mlb_hits(conn: sqlite3.Connection, token: str) -> dict:
    if not _table_exists(conn, "plate_appearances"):
        return {}
    try:                                       # tolerate a table missing batter columns
        rows = conn.execute(
            "SELECT CAST(batter_id AS TEXT) AS bid, SUM(is_hit) AS hits "
            "FROM plate_appearances WHERE game_date = ? GROUP BY batter_id", (token,)).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["bid"]: int(r["hits"] or 0) for r in rows}


def _mlb_pitcher_lines(conn: sqlite3.Connection, token: str) -> dict:
    """Per-pitcher K's and hits allowed that day, for pitchers who **started**
    (had a plate appearance in the 1st inning). ``{pitcher_id: {k, hits}}``."""
    if not _table_exists(conn, "plate_appearances"):
        return {}
    try:                                       # tolerate a table missing pitcher columns
        started = {str(r[0]) for r in conn.execute(
            "SELECT DISTINCT pitcher_id FROM plate_appearances "
            "WHERE game_date = ? AND inning IN ('1T', '1B')", (token,))}
        if not started:
            return {}
        rows = conn.execute(
            "SELECT CAST(pitcher_id AS TEXT) AS pid, SUM(is_strikeout) AS k, SUM(is_hit) AS hits "
            "FROM plate_appearances WHERE game_date = ? GROUP BY pitcher_id", (token,)).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["pid"]: {"k": int(r["k"] or 0), "hits": int(r["hits"] or 0)}
            for r in rows if r["pid"] in started}


def _wnba_lines(conn: sqlite3.Connection, token: str) -> dict:
    if not _table_exists(conn, "wnba_player_game_logs"):
        return {}
    rows = conn.execute(
        "SELECT CAST(player_id AS TEXT) AS pid, points, rebounds, assists, minutes "
        "FROM wnba_player_game_logs WHERE game_date = ?", (token,)).fetchall()
    return {r["pid"]: {"points": r["points"], "rebounds": r["rebounds"],
                       "assists": r["assists"], "minutes": r["minutes"]} for r in rows}


# ------------------------------------------------------------ READS (view) ----
def load_graded_slate(slate_date: date, *, min_score: float | None = None,
                      db_path: Path = DB_PATH) -> list[dict]:
    """Graded props for a slate, one row per (league, player, market) — the latest
    capture — sorted by score. ``min_score`` filters (default: all). Empty if the
    table/rows are absent."""
    token = slate_date.isoformat()
    cols = ("league", "player_id", "player_name", "team_name", "market", "market_key",
            "direction", "threshold", "opportunity_score", "stability_score", "result",
            "actual_value", "support_evidence", "risk_evidence", "captured_on")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            q = f"SELECT {', '.join(cols)} FROM {_SNAP} WHERE snapshot_date = ?"
            params: list = [token]
            if min_score is not None:
                q += " AND opportunity_score >= ?"
                params.append(min_score)
            q += " ORDER BY captured_on ASC"
            rows = conn.execute(q, params).fetchall()
        except sqlite3.OperationalError:
            return []
    latest: dict[tuple, dict] = {}          # keep last capture per prop
    for r in rows:
        latest[(r["league"], r["player_id"], r["market"])] = dict(r)
    out = list(latest.values())
    out.sort(key=lambda d: (d.get("opportunity_score") or 0), reverse=True)
    return out


def _tally(subset: list[dict]) -> dict:
    hit = sum(1 for r in subset if r.get("result") == "hit")
    miss = sum(1 for r in subset if r.get("result") == "miss")
    void = sum(1 for r in subset if r.get("result") == "void")
    pending = sum(1 for r in subset if r.get("result") in (None, "pending"))
    decided = hit + miss
    return {"hit": hit, "miss": miss, "void": void, "pending": pending,
            "total": len(subset), "hit_rate": (hit / decided) if decided else None}


def summarize(rows: list[dict]) -> dict:
    """Per-league and overall hit/miss/void counts + hit rate (voids excluded)."""
    leagues = sorted({r.get("league") for r in rows if r.get("league")})
    return {"overall": _tally(rows),
            "by_league": {lg: _tally([r for r in rows if r.get("league") == lg]) for lg in leagues}}


def summarize_by_market(rows: list[dict]) -> dict:
    """Per prop-type (batter hits, SP K, points, …) tallies, in canonical order.

    This is the Phase 2 payoff: it answers "which markets actually convert?" —
    hit rate broken out by market type rather than lumped together.
    """
    from domain.markets import ORDER, prop_type

    buckets: dict[str, list[dict]] = {}
    for r in rows:
        buckets.setdefault(prop_type(r.get("league"), r.get("market")), []).append(r)
    return {pt: _tally(buckets[pt]) for pt in ORDER if pt in buckets}
