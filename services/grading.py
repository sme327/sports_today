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
                f"SELECT rowid, league, game_id, player_id, market, market_key, direction, threshold "
                f"FROM {_SNAP} WHERE snapshot_date = ? {where}", (token,)).fetchall()
        except sqlite3.OperationalError:
            return summary
        if not rows:
            return summary

        mlb = _mlb_hits(conn, token)          # {batter_id: total_hits}
        mlb_tb = _mlb_total_bases(conn, token)  # {batter_id: total_bases}
        mlb_kbb = _mlb_batter_kbb(conn, token)  # {batter_id: {k, bb}}
        mlb_sp = _mlb_pitcher_lines(conn, token)  # {pitcher_id: {k, hits}} for starters
        # WNBA is matched by game_id, not date: the logs store game_date as a UTC
        # timestamp (a night game rolls to the next UTC day), so a date match never
        # aligns. {(game_id, player_id): line} plus the set of games actually loaded.
        wnba_lines, wnba_games = _wnba_lines_by_game(conn)
        # Data-availability gate: only grade a source once that date's results are
        # actually loaded. Otherwise a slate captured in the morning would grade to
        # all-void before its feed arrives, and idempotency would freeze that mistake.
        avail = {"mlb": _date_has_rows(conn, "plate_appearances", token)}
        graded_at = datetime.now().isoformat(timespec="seconds")

        for r in rows:
            result, actual, reason = _grade_row(r, mlb, mlb_tb, mlb_kbb, mlb_sp,
                                                wnba_lines, wnba_games, avail)
            if result is None:               # results genuinely not available yet
                summary["pending"] += 1
                continue
            conn.execute(
                f"UPDATE {_SNAP} SET result = ?, actual_value = ?, void_reason = ?, "
                f"graded_at = ? WHERE rowid = ?",
                (result, actual, reason, graded_at, r["rowid"]))
            summary["graded"] += 1
            summary[result] += 1
        conn.commit()
    return summary


def _grade_row(r, mlb: dict, mlb_tb: dict, mlb_kbb: dict, mlb_sp: dict, wnba_lines: dict,
               wnba_games: set, avail: dict) -> tuple[str | None, float | None, str | None]:
    """Grade one snapshot row via the market registry. Returns
    ``(result, actual_value, void_reason)``. Reads the stored ``market_key`` /
    ``direction`` when present, else resolves them from the legacy market text.

    Availability gates keep a row **pending** (None) rather than void when results
    aren't in yet: MLB by ``avail`` (date has a feed), WNBA by whether that specific
    game's box scores are loaded (``wnba_games``)."""
    key = _row_get(r, "market_key") or None
    direction = _row_get(r, "direction") or None
    if key is None:
        key, direction = markets.resolve(r["league"], r["market"])
    if key is None:
        return None, None, None             # unknown market → leave pending

    threshold = r["threshold"]
    pid = str(r["player_id"])

    if key == "batter_hit":
        if not avail["mlb"]:                 # results not loaded yet → pending, not void
            return None, None, None
        if pid not in mlb:
            return "void", None, "did not bat"
        actual = mlb[pid]
    elif key == "batter_tb":
        if not avail["mlb"]:
            return None, None, None
        if pid not in mlb_tb:
            return "void", None, "did not bat"
        actual = mlb_tb[pid]
    elif key in ("batter_k", "batter_bb"):
        if not avail["mlb"]:
            return None, None, None
        line = mlb_kbb.get(pid)
        if line is None:
            return "void", None, "did not bat"
        actual = line["k"] if key == "batter_k" else line["bb"]
    elif key in ("sp_k", "sp_hits"):
        if not avail["mlb"]:
            return None, None, None
        line = mlb_sp.get(pid)
        if line is None:
            return "void", None, "did not start"
        actual = line["k"] if key == "sp_k" else line["hits"]
    elif key in _WNBA_COL:
        gid = str(_row_get(r, "game_id") or "")
        if gid not in wnba_games:            # this game's box scores not loaded yet
            return None, None, None          # → pending, not void
        line = wnba_lines.get((gid, pid))
        if line is None or not line.get("minutes"):
            return "void", None, "did not play"
        actual = line.get(_WNBA_COL[key])
        if actual is None:
            return "void", None, "no box score"
    else:
        return None, None, None

    return markets.grade(key, actual, threshold, direction), float(actual), None


def _row_get(r, col):
    """sqlite3.Row has no .get(); tolerate rows that predate a column."""
    try:
        return r[col]
    except (IndexError, KeyError):
        return None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _date_has_rows(conn: sqlite3.Connection, table: str, token: str) -> bool:
    """Whether ``table`` has any results for ``game_date == token`` — i.e. that
    day's feed has been loaded. Missing table/column → treat as not-available."""
    if not _table_exists(conn, table):
        return False
    try:
        return conn.execute(
            f"SELECT 1 FROM {table} WHERE game_date = ? LIMIT 1", (token,)).fetchone() is not None
    except sqlite3.OperationalError:
        return False


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


def _mlb_total_bases(conn: sqlite3.Connection, token: str) -> dict:
    if not _table_exists(conn, "plate_appearances"):
        return {}
    try:
        rows = conn.execute(
            "SELECT CAST(batter_id AS TEXT) AS bid, SUM(total_bases) AS tb "
            "FROM plate_appearances WHERE game_date = ? GROUP BY batter_id", (token,)).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["bid"]: int(r["tb"] or 0) for r in rows}


def _mlb_batter_kbb(conn: sqlite3.Connection, token: str) -> dict:
    """Per-batter strikeouts and walks that day. ``{batter_id: {k, bb}}``."""
    if not _table_exists(conn, "plate_appearances"):
        return {}
    try:
        rows = conn.execute(
            "SELECT CAST(batter_id AS TEXT) AS bid, SUM(is_strikeout) AS k, SUM(is_walk) AS bb "
            "FROM plate_appearances WHERE game_date = ? GROUP BY batter_id", (token,)).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["bid"]: {"k": int(r["k"] or 0), "bb": int(r["bb"] or 0)} for r in rows}


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


def _wnba_lines_by_game(conn: sqlite3.Connection) -> tuple[dict, set]:
    """All WNBA box-score lines keyed by ``(game_id, player_id)``, plus the set of
    game_ids that have any loaded rows. Matching by game_id is timezone-proof — the
    logs' ``game_date`` is a UTC timestamp that can roll a night game to the next day,
    so a slate-date match fails. Missing table/column → empty (nothing gradeable)."""
    if not _table_exists(conn, "wnba_player_game_logs"):
        return {}, set()
    try:
        rows = conn.execute(
            "SELECT CAST(game_id AS TEXT) AS gid, CAST(player_id AS TEXT) AS pid, "
            "points, rebounds, assists, minutes FROM wnba_player_game_logs").fetchall()
    except sqlite3.OperationalError:
        return {}, set()
    lines = {(r["gid"], r["pid"]): {"points": r["points"], "rebounds": r["rebounds"],
                                    "assists": r["assists"], "minutes": r["minutes"]} for r in rows}
    return lines, {r["gid"] for r in rows}


# ------------------------------------------------------------ READS (view) ----
def load_graded_slate(slate_date: date, *, min_score: float | None = None,
                      db_path: Path = DB_PATH) -> list[dict]:
    """Graded props for a slate, one row per (league, player, market) — the latest
    capture — sorted by score. ``min_score`` filters (default: all). Empty if the
    table/rows are absent."""
    token = slate_date.isoformat()
    cols = ("league", "game_id", "player_id", "player_name", "team_name", "opponent",
            "opposing_sp", "market", "market_key", "direction", "threshold",
            "opportunity_score", "stability_score", "result", "actual_value",
            "void_reason", "support_evidence", "risk_evidence", "captured_on")
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


def load_graded_range(start: date, end: date, db_path: Path = DB_PATH) -> list[dict]:
    """All graded props with ``snapshot_date`` in ``[start, end]`` (inclusive), one
    row per (date, league, player, market) keeping the latest capture. Powers the
    Performance view. Each row carries its ``snapshot_date``."""
    cols = ("snapshot_date", "league", "game_id", "player_id", "player_name", "team_name",
            "opponent", "market", "market_key", "direction", "threshold",
            "opportunity_score", "result", "actual_value", "void_reason",
            "scoring_engine_version", "captured_on", "featured", "featured_rank")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            available = {row[1] for row in conn.execute(f"PRAGMA table_info({_SNAP})")}
            select_cols = [col for col in cols if col in available]
            rows = conn.execute(
                f"SELECT {', '.join(select_cols)} FROM {_SNAP} "
                f"WHERE snapshot_date BETWEEN ? AND ? ORDER BY captured_on ASC",
                (start.isoformat(), end.isoformat())).fetchall()
        except sqlite3.OperationalError:
            return []
    latest: dict[tuple, dict] = {}
    for r in rows:
        latest[(r["snapshot_date"], r["league"], r["player_id"], r["market"])] = dict(r)
    return with_featured_ranks(list(latest.values()))


def _tally(subset: list[dict]) -> dict:
    hit = sum(1 for r in subset if r.get("result") == "hit")
    miss = sum(1 for r in subset if r.get("result") == "miss")
    void = sum(1 for r in subset if r.get("result") == "void")
    pending = sum(1 for r in subset if r.get("result") in (None, "pending"))
    decided = hit + miss
    return {"hit": hit, "miss": miss, "void": void, "pending": pending,
            "total": len(subset), "hit_rate": (hit / decided) if decided else None}


def tally(rows: list[dict]) -> dict:
    """Public: hit/miss/void/pending counts + hit rate (voids+pending excluded) for a
    row subset. The single definition of a record/hit-rate, reused everywhere."""
    return _tally(rows)


def summarize(rows: list[dict]) -> dict:
    """Per-league and overall hit/miss/void counts + hit rate (voids excluded)."""
    leagues = sorted({r.get("league") for r in rows if r.get("league")})
    return {"overall": _tally(rows),
            "by_league": {lg: _tally([r for r in rows if r.get("league") == lg]) for lg in leagues}}


def summarize_by(rows: list[dict], key_fn) -> dict:
    """Group rows by ``key_fn(row)`` (None keys dropped) → {segment: tally}. Powers
    the edge finder and over/under breakdowns with one consistent tally."""
    buckets: dict = {}
    for r in rows:
        k = key_fn(r)
        if k is None or k == "":
            continue
        buckets.setdefault(k, []).append(r)
    return {k: _tally(v) for k, v in buckets.items()}


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


# --- Score bands (mutually-exclusive; the finer six) + sample gating -----------
MIN_SAMPLE = 30          # graded props below this = "small sample", don't over-trust

# The score at or above which a prop becomes a public qualifying prediction. All
# qualifying predictions appear on matchup pages; the highest-ranked eight are also
# featured on Today. Rows below the floor remain research observations.
CURATION_FLOOR = 70
FEATURED_MAX = 8


def split_served(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Compatibility alias returning ``(qualifying, research_only)`` populations."""
    served = [r for r in rows if (r.get("opportunity_score") or 0) >= CURATION_FLOOR]
    below = [r for r in rows if (r.get("opportunity_score") or 0) < CURATION_FLOOR]
    return served, below


def qualifying(rows: list[dict]) -> list[dict]:
    """Every public prediction clearing the publication floor."""
    return split_served(rows)[0]


def with_featured_ranks(rows: list[dict]) -> list[dict]:
    """Annotate latest-capture rows with the deterministic Today rank per slate.

    Persisted ``featured``/``featured_rank`` values win when present. Older ledger
    rows are reconstructed only from their stored pregame scores, never outcomes.
    """
    by_slate: dict[str, list[dict]] = {}
    for original in rows:
        row = dict(original)
        by_slate.setdefault(str(row.get("snapshot_date") or ""), []).append(row)
    out: list[dict] = []
    for slate_rows in by_slate.values():
        ordered = sorted(
            qualifying(slate_rows),
            key=lambda r: (-(r.get("opportunity_score") or 0), str(r.get("league") or ""),
                           str(r.get("player_name") or ""), str(r.get("market") or "")),
        )
        inferred = {id(row): rank for rank, row in enumerate(ordered[:FEATURED_MAX], 1)}
        for row in slate_rows:
            if row.get("featured") is None:
                rank = inferred.get(id(row))
                row["featured"] = bool(rank)
                row["featured_rank"] = rank
            else:
                row["featured"] = bool(row["featured"])
            out.append(row)
    return out

# (lo, hi, label) — inclusive, non-overlapping across the full qualifying range.
SCORE_BANDS: list[tuple[int, int, str]] = [
    (70, 74, "70–74"), (75, 79, "75–79"), (80, 84, "80–84"), (85, 89, "85–89"),
    (90, 94, "90–94"), (95, 98, "95–98"), (99, 100, "99–100"),
]


def band_of(score) -> str | None:
    s = score or 0
    for lo, hi, label in SCORE_BANDS:
        if lo <= s <= hi:
            return label
    return None


def decided(tally: dict) -> int:
    return tally["hit"] + tally["miss"]


def is_small_sample(tally: dict, min_sample: int = MIN_SAMPLE) -> bool:
    return decided(tally) < min_sample


def record(tally: dict) -> str:
    """Record as "H–M"."""
    return f"{tally['hit']}–{tally['miss']}"


def summarize_by_band(rows: list[dict], *, min_sample: int = MIN_SAMPLE) -> dict:
    """Per score band (the finer six), in order — the calibration signal. Each tally
    is flagged ``small_sample`` when its graded count is below ``min_sample``."""
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        b = band_of(r.get("opportunity_score"))
        if b:
            buckets.setdefault(b, []).append(r)
    out = {}
    for _lo, _hi, label in SCORE_BANDS:
        if label in buckets:
            t = _tally(buckets[label])
            t["small_sample"] = is_small_sample(t, min_sample)
            out[label] = t
    return out
