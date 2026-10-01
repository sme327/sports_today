"""The MLB postseason bracket, collected once per daily run and stored as a snapshot.

**Why a snapshot and not a live fetch.** The site is a static export, and the bracket
feeds up to sixteen pages (the bracket itself and one per series). Fetching per page
would turn one build into that many network calls, and a build that could not reach
StatsAPI would publish an empty bracket rather than yesterday's. One collection per run,
stored whole, keeps the pages consistent with each other and lets them say how old they
are.

**Why JSON, not rows.** The bracket is a small tree — thirteen series, at most 43 games,
twelve seeds, a handful of head-to-head records — read whole and never queried by
column. Flattening it into four tables would buy joins nobody runs.

What is stored is the source's own facts: the schedule of every series (placeholders
included), the seeds the final standings state, and each pairing's regular-season
head-to-head. Nothing here projects who wins.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from src.config import DB_PATH

TABLE = "mlb_postseason"


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            season INTEGER NOT NULL,
            snapshot_date TEXT NOT NULL,
            payload TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            PRIMARY KEY (season, snapshot_date)
        )
        """
    )


def fetch(season: int) -> dict:
    """Everything the bracket pages need, from three kinds of StatsAPI request."""
    from src import mlb_api

    series = mlb_api.postseason_series(season)
    try:
        seeds = mlb_api.postseason_seeds(season)
    except Exception:                                    # noqa: BLE001
        seeds = {}          # a bracket without seeds is still a bracket

    # Head-to-head for every pairing whose two clubs are both known. At most fifteen
    # requests in a whole October, and usually a handful.
    pairs: set[tuple[str, str]] = set()
    for entry in series:
        for game in entry["games"]:
            if game["away_placeholder"] or game["home_placeholder"]:
                continue
            a, h = str(game["away_id"]), str(game["home_id"])
            pairs.add(tuple(sorted((a, h))))
    head_to_head: dict[str, dict[str, int]] = {}
    for a, h in sorted(pairs):
        try:
            head_to_head[f"{a}-{h}"] = mlb_api.head_to_head(season, a, h)
        except Exception:                                # noqa: BLE001
            continue
    return {"season": season, "series": series, "seeds": seeds,
            "head_to_head": head_to_head}


def store(payload: dict, on: date, db_path: Path = DB_PATH) -> None:
    collected = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as conn:
        ensure_tables(conn)
        conn.execute(
            f"INSERT OR REPLACE INTO {TABLE} (season, snapshot_date, payload, collected_at) "
            "VALUES (?, ?, ?, ?)",
            (int(payload["season"]), on.isoformat(), json.dumps(payload), collected),
        )
        conn.commit()


def collect(on: date | None = None, db_path: Path = DB_PATH) -> int:
    """Fetch and store today's bracket. Returns the number of series stored.

    Silent (0, nothing written) when the season has no postseason schedule yet, which
    is most of the year.
    """
    today = on or date.today()
    payload = fetch(today.year)
    if not payload["series"]:
        return 0
    store(payload, today, db_path)
    return len(payload["series"])


def load(as_of: date | None = None, db_path: Path = DB_PATH) -> dict | None:
    """The newest bracket snapshot on or before ``as_of``, with its collection time.

    Bounded by date for the same reason standings are: a page rebuilt later must read
    the bracket as it stood on its own day.
    """
    day = (as_of or date.today()).isoformat()
    try:
        with sqlite3.connect(db_path) as conn:
            ensure_tables(conn)
            row = conn.execute(
                f"SELECT payload, collected_at, snapshot_date FROM {TABLE} "
                "WHERE snapshot_date <= ? ORDER BY snapshot_date DESC LIMIT 1",
                (day,),
            ).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    payload = json.loads(row[0])
    payload["collected_at"] = row[1]
    payload["snapshot_date"] = row[2]
    return payload


if __name__ == "__main__":
    print(f"Stored {collect()} postseason series.")
