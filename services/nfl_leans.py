"""The prop-lean ledger: every over/under a person wrote on an NFL matchup page,
recorded when the page was published and graded from the box score once the game is
final. Hit rates here are **descriptive** — a dozen leans is not a sample, and the page
that shows them says so.

Record is idempotent and never overwrites a grade. Grade is only ever applied to a game
ESPN reports as final, and a player missing from the box score is a **void** (he did
not play), never a zero — the same vocabulary the prop ledger uses (hit / miss / void).
"""

from __future__ import annotations

import sqlite3
from collections import OrderedDict
from datetime import date, datetime, timezone
from pathlib import Path

from services.nfl_game_notes import (
    LEAN_STATS, NOTES_DIR, VOLUME_STATS, GameNotes, load_notes, notes_path,
)
from src.config import DB_PATH

TABLE = "nfl_lean_ledger"


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            game_id TEXT NOT NULL,
            kickoff TEXT NOT NULL,
            away TEXT NOT NULL,
            home TEXT NOT NULL,
            team TEXT NOT NULL,
            player TEXT NOT NULL,
            stat TEXT NOT NULL,
            line REAL NOT NULL,
            direction TEXT NOT NULL,
            section TEXT NOT NULL DEFAULT 'leans',
            rank INTEGER NOT NULL,
            confidence TEXT NOT NULL,
            why TEXT NOT NULL,
            authored TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            actual REAL,
            result TEXT,
            graded_at TEXT,
            PRIMARY KEY (game_id, player, stat, line, direction)
        )
    """)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record(notes: GameNotes, db_path: Path = DB_PATH) -> int:
    """Upsert the note's leans. A re-record (the note was edited) refreshes rank, why,
    confidence and the fingerprint but keeps any grade already applied. Returns the
    number of rows written."""
    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        n = 0
        ranks: dict[str, int] = {}
        for lean in notes.leans:
            ranks[lean.section] = rank = ranks.get(lean.section, 0) + 1
            # A pass is an evaluated line with no call: recorded so "3 leans of 17
            # evaluated" can be said, with its result "pass" from the start so the
            # grader never touches it.
            result = "pass" if lean.direction == "pass" else None
            conn.execute(f"""
                INSERT INTO {TABLE} (game_id, kickoff, away, home, team, player, stat, line,
                    direction, section, rank, confidence, why, authored, fingerprint,
                    recorded_at, result)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(game_id, player, stat, line, direction) DO UPDATE SET
                    section = excluded.section, rank = excluded.rank,
                    confidence = excluded.confidence, why = excluded.why,
                    authored = excluded.authored, fingerprint = excluded.fingerprint,
                    kickoff = excluded.kickoff
            """, (notes.game_id, notes.kickoff, notes.away, notes.home, lean.team,
                  lean.player, lean.stat, lean.line, lean.direction, lean.section, rank,
                  lean.confidence, lean.why, notes.authored, notes.fingerprint, _now(),
                  result))
            n += 1
        conn.commit()
    return n


def record_all(notes_dir: Path = NOTES_DIR, db_path: Path = DB_PATH) -> dict[str, int]:
    """Record every note file on disk. Cheap, idempotent, and how the daily run keeps
    the ledger current without anyone remembering to."""
    out: dict[str, int] = {}
    for path in sorted(Path(notes_dir).glob("*.toml")):
        notes = load_notes(path.stem, notes_dir)
        if notes is not None:
            out[notes.game_id] = record(notes, db_path)
    return out


def grade_value(direction: str, line: float, actual: float) -> str:
    """hit / miss, or void on a push — a whole-number line that lands exactly."""
    if actual == line:
        return "void"
    if direction == "under":
        return "hit" if actual < line else "miss"
    return "hit" if actual > line else "miss"


def grade_game(game_id: str, boxscore: dict, db_path: Path = DB_PATH) -> dict[str, int]:
    """Apply a parsed box score (``src.espn_nfl_boxscore.parse_summary``) to the game's
    ungraded rows. Refuses a game that is not final. A player absent from the box score
    is voided: he did not play, and 0 receptions would grade an under as a hit."""
    if not boxscore.get("final"):
        return {"skipped_not_final": 1}
    players = boxscore.get("players") or {}
    tally = {"hit": 0, "miss": 0, "void": 0}
    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        rows = conn.execute(
            f"SELECT player, stat, line, direction FROM {TABLE} "
            f"WHERE game_id = ? AND result IS NULL", (game_id,)).fetchall()
        for player, stat, line, direction in rows:
            stats = players.get(player)
            if stats is None:
                actual, result = None, "void"
            else:
                actual = float(stats.get(stat, 0.0))
                result = grade_value(direction, float(line), actual)
            conn.execute(
                f"UPDATE {TABLE} SET actual = ?, result = ?, graded_at = ? "
                f"WHERE game_id = ? AND player = ? AND stat = ? AND line = ? AND direction = ?",
                (actual, result, _now(), game_id, player, stat, line, direction))
            tally[result] += 1
        conn.commit()
    return tally


def games_due(db_path: Path = DB_PATH, today: date | None = None) -> list[str]:
    """Game ids with ungraded rows whose kickoff date has arrived (the grader still
    checks ESPN's own final flag before touching anything)."""
    today = today or date.today()
    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        rows = conn.execute(
            f"SELECT DISTINCT game_id FROM {TABLE} WHERE result IS NULL AND kickoff <= ?",
            (today.isoformat(),)).fetchall()
    return [r[0] for r in rows]


def grade_due(db_path: Path = DB_PATH, today: date | None = None,
              fetch=None) -> dict[str, dict]:
    """Grade every due game, fetching each box score once. ``fetch`` is injectable
    for tests; the default is the ESPN client."""
    if fetch is None:
        from src.espn_nfl_boxscore import fetch_boxscore as fetch
    out: dict[str, dict] = {}
    for game_id in games_due(db_path, today):
        out[game_id] = grade_game(game_id, fetch(game_id), db_path)
    return out


# --- reading ---------------------------------------------------------------------

def load(db_path: Path = DB_PATH) -> list[dict]:
    """Every ledger row, newest game first, then by rank. Missing table → []."""
    if not Path(db_path).is_file():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_table(conn)
        rows = conn.execute(
            f"SELECT * FROM {TABLE} ORDER BY kickoff DESC, game_id, section, rank").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["stat_label"] = LEAN_STATS.get(d["stat"], d["stat"])
        out.append(d)
    return out


def _tally(rows: list[dict]) -> dict:
    t = {"hit": 0, "miss": 0, "void": 0, "pending": 0, "pass": 0}
    for r in rows:
        t[r["result"] or "pending"] += 1
    decided = t["hit"] + t["miss"]
    t["decided"] = decided
    t["evaluated"] = len(rows)
    t["called"] = len(rows) - t["pass"]
    t["hit_rate"] = (t["hit"] / decided) if decided else None
    return t


def summarize(rows: list[dict]) -> dict:
    """Overall plus by confidence, by direction, by stat and by game — each a tally with
    ``hit_rate`` None until something is decided, so a page never prints a bare 0%."""
    def by(key, order=None, skip_pass: bool = False):
        groups: "OrderedDict[str, list]" = OrderedDict()
        for r in rows:
            if skip_pass and r["direction"] == "pass":
                continue
            groups.setdefault(str(r[key]), []).append(r)
        keys = [k for k in (order or []) if k in groups] + \
               [k for k in groups if k not in (order or [])]
        return OrderedDict((k, _tally(groups[k])) for k in keys)

    games: "OrderedDict[str, dict]" = OrderedDict()
    for r in rows:
        g = games.setdefault(r["game_id"], {
            "game_id": r["game_id"], "kickoff": r["kickoff"], "away": r["away"],
            "home": r["home"], "rows": []})
        g["rows"].append(r)
    for g in games.values():
        g["tally"] = _tally(g["rows"])
    return {
        "overall": _tally(rows),
        # Volume plays cut across sections: every attempts / completions / receptions
        # call, wherever it was made. The owner's hunch is that this is where the edge
        # lives, so it gets its own running record.
        "volume": _tally([r for r in rows if r["stat"] in VOLUME_STATS]),
        "by_section": by("section", ["props", "leans", "overs", "volume"]),
        # a pass has no confidence tier, so it is not a row in this split
        "by_confidence": by("confidence", ["high", "moderate", "low"], skip_pass=True),
        "by_direction": by("direction", ["under", "over", "pass"]),
        "by_stat": OrderedDict((LEAN_STATS.get(k, k), v) for k, v in by("stat").items()),
        "games": list(games.values()),
    }


def notes_for(game_id: str, notes_dir: Path = NOTES_DIR) -> bool:
    return notes_path(game_id, notes_dir).is_file()
