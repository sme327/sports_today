"""Pick up a new NFL season feed during the daily rebuild, if one has been dropped.

MLB's feed is replaced every morning and the pipeline knows it. NFL's was not in the
pipeline at all: `scripts/import_nfl_feed` auto-detects a feed pair in Downloads, but
nothing ever called it, so keeping the current season loaded meant remembering to run it
by hand each week. That is the whole gap between "the slate↔feed bridge works" and "the
bridge works *on this season's games*".

**Idempotent by fingerprint.** The rebuild runs daily and an NFL player feed is ~9MB;
re-parsing the same workbook every morning is pure waste. Each import records the source
files' name+size+mtime, and a run whose fingerprint matches the last one is skipped
without opening the workbook.

**Silence is the normal case.** Most days — and the entire offseason — there is no new
feed. That is not a warning; it returns a `skipped` status and says nothing.

**Non-fatal by construction.** A malformed NFL workbook must never take down the MLB
daily update, so the caller treats any failure as a note, exactly like WNBA and MLS.
"""

from __future__ import annotations

import glob
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.config import DB_PATH

_TABLE = "nfl_feed_runs"

# **Downloads only, and deliberately so.** The manual CLI (`scripts/import_nfl_feed`)
# also searches ~/Documents, which is fine when a human invokes it and names the file.
# An *automated* daily job must not go hunting through someone's documents tree and
# import whatever it happens to find — the first version of this did exactly that and
# picked up a feed from a personal "to review" folder. Downloads is the drop location the
# MLB pipeline already uses, so it is the one place a file arriving means "load me".
_SEARCH_DIRS = (Path.home() / "Downloads",)


@dataclass(frozen=True)
class RefreshResult:
    status: str                 # "imported" | "skipped" | "unchanged"
    message: str
    seasons: tuple[int, ...] = ()
    team_rows: int = 0
    player_rows: int = 0


def _newest(pattern: str, dirs=_SEARCH_DIRS) -> Path | None:
    hits: list[str] = []
    for d in dirs:
        if d.exists():
            hits += glob.glob(str(d / "**" / pattern), recursive=True)
    return Path(max(hits, key=lambda p: Path(p).stat().st_mtime)) if hits else None


def _fingerprint(*paths: Path) -> str:
    """Name + size + mtime for each source file. Cheap, and enough to notice a re-download
    of the same week (which would re-import identical rows for no benefit)."""
    parts = []
    for p in paths:
        s = p.stat()
        parts.append(f"{p.name}:{s.st_size}:{int(s.st_mtime)}")
    return "|".join(parts)


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ran_at TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            team_file TEXT, player_file TEXT,
            seasons TEXT, team_rows INTEGER, player_rows INTEGER,
            status TEXT, message TEXT
        )""")


def _last_fingerprint(db_path: Path) -> str | None:
    if not Path(db_path).exists():
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            _ensure(conn)
            row = conn.execute(
                f"SELECT fingerprint FROM {_TABLE} WHERE status='imported' "
                f"ORDER BY run_id DESC LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def refresh(db_path: str | Path = DB_PATH, dirs=_SEARCH_DIRS,
            force: bool = False) -> RefreshResult:
    """Import a newly-dropped NFL feed pair, or explain why nothing happened."""
    team = _newest("*nfl-season-team-feed*.xlsx", dirs)
    player = _newest("*nfl-season-player-feed*.xlsx", dirs)
    if not team or not player:
        return RefreshResult("skipped", "No NFL feed pair in Downloads.")

    fp = _fingerprint(team, player)
    if not force and fp == _last_fingerprint(Path(db_path)):
        return RefreshResult("unchanged", f"NFL feed unchanged since the last import "
                                          f"({team.name}).")

    from src.nfl_ingest import import_nfl_feeds
    counts = import_nfl_feeds(team, player, Path(db_path))
    seasons = tuple(int(s) for s in counts["seasons"])
    with sqlite3.connect(db_path) as conn:
        _ensure(conn)
        conn.execute(
            f"""INSERT INTO {_TABLE} (ran_at, fingerprint, team_file, player_file,
                    seasons, team_rows, player_rows, status, message)
                VALUES (?,?,?,?,?,?,?,?,?)""",
            (datetime.now(timezone.utc).isoformat(), fp, team.name, player.name,
             ",".join(str(s) for s in seasons), counts["team_games"], counts["player_games"],
             "imported", f"Imported {counts['games']} games through week {counts['weeks']}."))
    return RefreshResult(
        "imported",
        f"NFL feed imported: {counts['games']} games through week {counts['weeks']} "
        f"(season {', '.join(str(s) for s in seasons)}).",
        seasons, counts["team_games"], counts["player_games"])
