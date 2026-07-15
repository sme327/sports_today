from datetime import date

from services.data_access import load_plate_appearances, load_wnba_player_logs


def test_as_of_excludes_slate_date_and_later(tmp_db):
    # Data spans 2026-06-01 .. 2026-06-10.
    bounded = load_plate_appearances(as_of=date(2026, 6, 10), db_path=tmp_db)
    assert not bounded.empty
    assert bounded["game_date"].max().date() < date(2026, 6, 10)  # no leakage


def test_full_load_includes_all(tmp_db):
    full = load_plate_appearances(db_path=tmp_db)
    assert full["game_date"].max().date() == date(2026, 6, 10)


def test_wnba_as_of_bounds_on_date_prefix(tmp_db):
    bounded = load_wnba_player_logs(as_of=date(2026, 6, 8), db_path=tmp_db)
    assert len(bounded) == 1  # only the 2026-06-01 game, not 06-08


def test_missing_db_returns_empty(tmp_path):
    missing = tmp_path / "nope.db"
    assert load_plate_appearances(db_path=missing).empty
    assert load_wnba_player_logs(db_path=missing).empty
