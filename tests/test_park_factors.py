"""Ballpark as evidence: a measured effect the scorer is not allowed to use.

Folded into batter-hit scoring it widened the quartile spread and lifted correlation,
both intervals clear of zero, but left the top 20% unmoved — and the top is the only
part any surface serves. It failed the ship gate (decision log 2026-08-31). Said out
loud on the page it needs no gate, because it changes no ranking. These cover the two
things that keeps honest: it stays silent when it has nothing to say, and it never
reaches back past the slate for the data it describes.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from services import park_factors


def _db(tmp_path, rows, games):
    path = tmp_path / "p.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE games (game_id TEXT, road_team TEXT)")
    conn.execute("CREATE TABLE plate_appearances "
                 "(game_id TEXT, game_date TEXT, batting_team TEXT, is_hit INT)")
    conn.executemany("INSERT INTO games VALUES (?, ?)", games)
    conn.executemany("INSERT INTO plate_appearances VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    return path


@pytest.fixture(autouse=True)
def _clear():
    park_factors.clear_cache()
    yield
    park_factors.clear_cache()


def _season(rate_at_park, rate_elsewhere, n=700):
    """The same visiting team plays half its games in one park and half in another.

    Both sides of every game need plate appearances: the park is identified as the home
    team, which is derived as "the side that is not the road team", and that needs two
    teams present to resolve.
    """
    rows, games = [], []
    for i in range(n):
        # At Rockies' park, the visitor hits at rate_at_park.
        games.append((f"h{i}", "Padres"))
        rows.append((f"h{i}", "2026-05-01", "Padres", 1 if i % 100 < rate_at_park else 0))
        rows.append((f"h{i}", "2026-05-01", "Rockies", 1 if i % 100 < 30 else 0))
        # At Giants' park, the same visitor hits at rate_elsewhere.
        games.append((f"n{i}", "Padres"))
        rows.append((f"n{i}", "2026-05-01", "Padres", 1 if i % 100 < rate_elsewhere else 0))
        rows.append((f"n{i}", "2026-05-01", "Giants", 1 if i % 100 < 30 else 0))
    return rows, games


def test_a_park_that_moves_hits_says_so(tmp_path):
    rows, games = _season(40, 20)
    note = park_factors.note_for("Rockies", date(2026, 6, 1), db_path=_db(tmp_path, rows, games))
    assert note is not None and "above average here" in note


def test_a_neutral_park_says_nothing(tmp_path):
    """The true spread between parks is about +/-4%, so a smaller difference is noise
    dressed as insight. Most parks get no note, and that is the point."""
    rows, games = _season(30, 30)
    assert park_factors.note_for("Rockies", date(2026, 6, 1),
                                 db_path=_db(tmp_path, rows, games)) is None


def test_a_thin_sample_says_nothing(tmp_path):
    rows, games = _season(40, 20, n=40)
    assert park_factors.note_for("Rockies", date(2026, 6, 1),
                                 db_path=_db(tmp_path, rows, games)) is None


def test_only_games_before_the_slate_are_read(tmp_path):
    """The as_of rule: a park note for an April game must not be computed from July."""
    rows, games = _season(40, 20)
    db = _db(tmp_path, rows, games)
    # Everything above is dated 2026-05-01, so a slate on that day sees nothing prior.
    assert park_factors.note_for("Rockies", date(2026, 5, 1), db_path=db) is None
    park_factors.clear_cache()
    assert park_factors.note_for("Rockies", date(2026, 6, 1), db_path=db) is not None


def test_an_unknown_park_and_a_missing_database_stay_quiet(tmp_path):
    rows, games = _season(40, 20)
    db = _db(tmp_path, rows, games)
    assert park_factors.note_for("Nobody's Park", date(2026, 6, 1), db_path=db) is None
    assert park_factors.note_for(None, date(2026, 6, 1), db_path=db) is None
    assert park_factors.note_for("Rockies", date(2026, 6, 1),
                                 db_path=tmp_path / "missing.db") is None


def test_the_note_never_predicts():
    """Product rule: this is description. It must not acquire forecasting words."""
    import inspect

    source = inspect.getsource(park_factors.note_for)
    for banned in ("expect", "should", "likely", "projected", "favour", "favor"):
        assert banned not in source.lower().split('"""')[-1]
