from __future__ import annotations

from datetime import date

from services import matchup_cache


def test_matchup_model_round_trip_and_engine_version_isolation(tmp_path):
    db = tmp_path / "sports.db"
    page = {"hero": "Mariners at Rangers", "sections": ("identity", "matchups")}
    matchup_cache.store("MLB", "401", date(2026, 8, 15), "v1", page, db_path=db)

    assert matchup_cache.load("MLB", "401", date(2026, 8, 15), "v1", db_path=db) == page
    assert matchup_cache.load("MLB", "401", date(2026, 8, 15), "v2", db_path=db) is None
