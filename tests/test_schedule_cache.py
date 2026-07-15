from datetime import date

from domain.models import SlateGame, SourceStatus
from services import schedule_cache


def _game(gid="1"):
    return SlateGame(league="MLB", game_id=gid, away_short="SEA", home_short="HOU")


def test_round_trip(tmp_path):
    db = tmp_path / "c.db"
    schedule_cache.write(
        league="MLB", slate_date=date(2026, 7, 15), source="src",
        status=SourceStatus.LIVE, games=[_game()], db_path=db,
    )
    res = schedule_cache.read_latest_usable(league="MLB", slate_date=date(2026, 7, 15), db_path=db)
    assert res is not None
    games, _ = res
    assert games[0].away_display == "SEA"


def test_empty_result_not_usable(tmp_path):
    db = tmp_path / "c.db"
    schedule_cache.write(
        league="WNBA", slate_date=date(2026, 7, 15), source="src",
        status=SourceStatus.EMPTY, games=[], db_path=db,
    )
    assert schedule_cache.read_latest_usable(league="WNBA", slate_date=date(2026, 7, 15), db_path=db) is None


def test_missing_db_returns_none(tmp_path):
    assert schedule_cache.read_latest_usable(
        league="MLB", slate_date=date(2026, 7, 15), db_path=tmp_path / "nope.db"
    ) is None
