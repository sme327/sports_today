from __future__ import annotations

import sqlite3
from datetime import date, datetime

from domain.models import DataStatus, Opportunity, OpportunityMode, SlateGame, SourceStatus
from services import daily_feed, schedule_cache


def _opportunity() -> Opportunity:
    return Opportunity(
        league="MLB",
        player_id="17",
        player_name="Test Player",
        team_id="SEA",
        team_name="Mariners",
        market="1+ Hit",
        market_key="batter_hit",
        direction="over",
        threshold=1,
        opportunity_score=91,
        stability_score=78,
        supporting_evidence=["Strong recent contact"],
        negative_evidence=["Limited sample"],
        recent_line=[0, 1, 2],
        line_threshold=1,
        image_url="https://example.com/team.png",
        headshot_url="https://example.com/player.png",
        game_id="g1",
        mode=OpportunityMode.SLATE,
        components={"form": 0.8},
        data_status=DataStatus("test", SourceStatus.CACHED, datetime(2026, 8, 15, 8)),
    )


def test_daily_feed_round_trip_is_lossless_for_display_fields(tmp_path):
    db = tmp_path / "sports.db"
    daily_feed.store(date(2026, 8, 15), [_opportunity()], db_path=db)
    loaded, calculated_at = daily_feed.load(date(2026, 8, 15), db_path=db)

    assert calculated_at is not None
    assert len(loaded) == 1
    actual = loaded[0]
    assert actual.player_name == "Test Player"
    assert actual.recent_line == [0, 1, 2]
    assert actual.line_cleared == [False, True, True]
    assert actual.headshot_url.endswith("player.png")
    assert actual.data_status.status is SourceStatus.CACHED


def test_cached_schedule_reader_includes_legitimate_empty_slates(tmp_path):
    db = tmp_path / "sports.db"
    fetched = datetime(2026, 8, 15, 7, 30)
    schedule_cache.write(
        league="MLB",
        slate_date=date(2026, 8, 15),
        source="MLB StatsAPI",
        status=SourceStatus.EMPTY,
        games=[],
        fetched_at=fetched,
        db_path=db,
    )
    cached = schedule_cache.read_latest(
        league="MLB", slate_date=date(2026, 8, 15), db_path=db
    )
    assert cached is not None
    games, status, actual_fetched, source = cached
    assert games == []
    assert status is SourceStatus.EMPTY
    assert actual_fetched == fetched
    assert source == "MLB StatsAPI"
