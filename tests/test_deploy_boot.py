"""The app must boot against a fresh, empty database (e.g. a cloud deploy with no
local MLB workbook): `ensure_schema` creates the DB + additive tables, and every
data read degrades to an empty result instead of crashing. Live-schedule leagues
then work; leagues without loaded history show honest empty states."""

from __future__ import annotations

import sqlite3
from datetime import date

from services.migrations import ensure_schema
from services.data_access import load_plate_appearances, load_wnba_player_logs
from services import mls_repository as R


def test_fresh_db_migrates_and_reads_degrade(tmp_path):
    db = tmp_path / "fresh.db"
    assert not db.exists()
    ensure_schema(db)                                    # creates the DB from nothing
    assert db.exists()

    tables = {r[0] for r in sqlite3.connect(db).execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    # additive tables the app queries are present; unloaded league tables are absent
    assert {"schedule_cache", "mls_matches", "mls_match_events"} <= tables
    assert "plate_appearances" not in tables and "wnba_player_game_logs" not in tables

    # every read the homepage performs must return empty, not raise
    assert load_plate_appearances(as_of=date.today(), db_path=db).empty
    assert load_wnba_player_logs(as_of=date.today(), db_path=db).empty
    assert R.team_match_frame(date.today(), db_path=db).empty
    assert R.team_event_patterns("1", date.today(), db_path=db)["goals"] == 0
    assert R.standings_lookup("1", date.today(), db_path=db) is None
