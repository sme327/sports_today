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

from src.config import DB_PATH

_SNAP = "opportunity_snapshots"


def _wnba_stat_column(market: str) -> str | None:
    m = (market or "").lower()
    if "point" in m:
        return "points"
    if "rebound" in m:
        return "rebounds"
    if "assist" in m:
        return "assists"
    return None


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
                f"SELECT rowid, league, player_id, market, threshold "
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
    league = r["league"]
    threshold = r["threshold"]
    pid = str(r["player_id"])
    if league == "MLB":
        market_raw = r["market"] or ""
        market = market_raw.lower()
        is_sp = "strikeout" in market or "hits allowed" in market
        if is_sp:
            line = mlb_sp.get(pid)
            if line is None:
                return "void", None        # did not start
            actual = line["k"] if "strikeout" in market else line["hits"]
            # Direction is encoded in the label: "≤ T …" is an under, "T+ …" an over.
            under = market_raw.strip().startswith("≤")
            hit = actual <= (threshold or 0) if under else actual >= (threshold or 0)
            return ("hit" if hit else "miss"), float(actual)
        if pid not in mlb:                  # batter 1+ Hit
            return "void", None            # did not bat that day
        hits = mlb[pid]
        return ("hit" if hits >= (threshold or 1) else "miss"), float(hits)
    if league == "WNBA":
        line = wnba.get(pid)
        col = _wnba_stat_column(r["market"])
        if line is None or col is None:
            return "void", None            # not in the box score
        if not line.get("minutes"):        # zero/NULL minutes → did not play
            return "void", None
        actual = line.get(col)
        if actual is None:
            return "void", None
        return ("hit" if actual >= (threshold or 0) else "miss"), float(actual)
    return None, None                       # unknown league → leave pending


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
    cols = ("league", "player_id", "player_name", "team_name", "market", "threshold",
            "opportunity_score", "stability_score", "result", "actual_value",
            "support_evidence", "risk_evidence", "captured_on")
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


def summarize(rows: list[dict]) -> dict:
    """Per-league and overall hit/miss/void counts + hit rate (voids excluded)."""
    def tally(subset):
        hit = sum(1 for r in subset if r.get("result") == "hit")
        miss = sum(1 for r in subset if r.get("result") == "miss")
        void = sum(1 for r in subset if r.get("result") == "void")
        pending = sum(1 for r in subset if r.get("result") in (None, "pending"))
        decided = hit + miss
        return {"hit": hit, "miss": miss, "void": void, "pending": pending,
                "total": len(subset), "hit_rate": (hit / decided) if decided else None}

    leagues = sorted({r.get("league") for r in rows if r.get("league")})
    return {"overall": tally(rows),
            "by_league": {lg: tally([r for r in rows if r.get("league") == lg]) for lg in leagues}}
