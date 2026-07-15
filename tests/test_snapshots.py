import sqlite3
from datetime import date, datetime

from domain.models import DataStatus, Opportunity, OpportunityMode, SourceStatus
from services.migrations import ensure_schema
from services import snapshots


def _opp():
    return Opportunity(
        league="MLB", player_id="p1", player_name="Test", team_id=None,
        team_name="Mariners", market="1+ Hit", threshold=1,
        opportunity_score=88, stability_score=70,
        supporting_evidence=["a"], negative_evidence=["b"],
        components={"x": 1.0}, mode=OpportunityMode.SLATE, game_id="1",
    )


def test_write_captures_context_once_per_day(tmp_path):
    db = tmp_path / "s.db"
    ensure_schema(db)
    status = {"MLB": DataStatus("MLB StatsAPI", SourceStatus.LIVE, datetime.now())}
    n1 = snapshots.write_daily_snapshot(
        slate_date=date(2026, 7, 15), as_of=date(2026, 7, 15),
        opportunities=[_opp()], schedule_status=status, db_path=db,
    )
    n2 = snapshots.write_daily_snapshot(
        slate_date=date(2026, 7, 15), as_of=date(2026, 7, 15),
        opportunities=[_opp()], schedule_status=status, db_path=db,
    )
    assert n1 == 1
    assert n2 == 0  # idempotent per slate per day
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT schedule_source_status, historical_data_cutoff, "
            "lineups_available, scoring_engine_version FROM opportunity_snapshots"
        ).fetchone()
    assert row == ("live", "2026-07-15", 0, "mlb-1hit-v0.1")


def test_no_opportunities_writes_nothing(tmp_path):
    db = tmp_path / "s.db"
    ensure_schema(db)
    assert snapshots.write_daily_snapshot(
        slate_date=date(2026, 7, 15), as_of=date(2026, 7, 15),
        opportunities=[], db_path=db,
    ) == 0
