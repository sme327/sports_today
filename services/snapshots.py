"""Daily opportunity snapshots.

Persists not just the score but the context needed to reproduce/interpret a
ranking later (owner decision 1, section 3.2): data cutoff, schedule provenance,
and which context (lineups / matchup / injuries) was available at capture time.
No snapshot-review UI is built in this pass — this is the storage seam plus the
write path.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from domain.models import DataStatus, Opportunity
from src.config import DB_PATH

_TABLE = "opportunity_snapshots"

# Engine versions per league (kept next to each adapter).
ENGINE_VERSIONS = {
    "MLB": "mlb-1hit-v0.1",
    "WNBA": "wnba-pra-v0.1",
}


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            snapshot_date TEXT NOT NULL,
            captured_on TEXT NOT NULL,
            calculated_at TEXT NOT NULL,
            league TEXT NOT NULL,
            game_id TEXT,
            player_id TEXT NOT NULL,
            player_name TEXT,
            team_id TEXT,
            team_name TEXT,
            market TEXT NOT NULL,
            threshold REAL,
            mode TEXT,
            opportunity_score INTEGER,
            stability_score INTEGER,
            component_values TEXT,
            support_evidence TEXT,
            risk_evidence TEXT,
            schedule_source_status TEXT,
            historical_data_cutoff TEXT,
            lineups_available INTEGER,
            matchup_context_available INTEGER,
            injury_context_available INTEGER,
            scoring_engine_version TEXT,
            PRIMARY KEY (snapshot_date, captured_on, league, player_id, market)
        )
        """
    )


def _already_captured(conn: sqlite3.Connection, slate_token: str, captured_on: str) -> bool:
    row = conn.execute(
        f"SELECT 1 FROM {_TABLE} WHERE snapshot_date=? AND captured_on=? LIMIT 1",
        (slate_token, captured_on),
    ).fetchone()
    return row is not None


def write_daily_snapshot(
    *,
    slate_date: date,
    as_of: date,
    opportunities: list[Opportunity],
    schedule_status: dict[str, DataStatus] | None = None,
    db_path: Path = DB_PATH,
    # Context availability — all False in this pass (honestly not yet included).
    lineups_available: bool = False,
    matchup_context_available: bool = False,
    injury_context_available: bool = False,
) -> int:
    """Write one snapshot per opportunity for ``slate_date``.

    Idempotent per day: if a snapshot already exists for this slate date and
    today's capture date, nothing is written. Returns rows written.
    """
    if not opportunities:
        return 0
    now = datetime.now()
    slate_token = slate_date.isoformat()
    captured_on = now.date().isoformat()
    schedule_status = schedule_status or {}

    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        if _already_captured(conn, slate_token, captured_on):
            return 0
        written = 0
        for opp in opportunities:
            status = schedule_status.get(opp.league)
            conn.execute(
                f"""
                INSERT OR IGNORE INTO {_TABLE} (
                    snapshot_date, captured_on, calculated_at, league, game_id,
                    player_id, player_name, team_id, team_name, market, threshold,
                    mode, opportunity_score, stability_score, component_values,
                    support_evidence, risk_evidence, schedule_source_status,
                    historical_data_cutoff, lineups_available,
                    matchup_context_available, injury_context_available,
                    scoring_engine_version
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    slate_token,
                    captured_on,
                    now.isoformat(timespec="seconds"),
                    opp.league,
                    opp.game_id,
                    opp.player_id,
                    opp.player_name,
                    opp.team_id,
                    opp.team_name,
                    opp.market,
                    float(opp.threshold) if opp.threshold is not None else None,
                    opp.mode.value,
                    opp.opportunity_score,
                    opp.stability_score,
                    json.dumps(opp.components),
                    json.dumps(opp.supporting_evidence),
                    json.dumps(opp.negative_evidence),
                    status.status.value if status else None,
                    as_of.isoformat(),
                    int(lineups_available),
                    int(matchup_context_available),
                    int(injury_context_available),
                    ENGINE_VERSIONS.get(opp.league),
                ),
            )
            written += 1
        conn.commit()
    return written
