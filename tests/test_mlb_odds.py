"""Reconciling MLB market lines across two feed vintages.

Offline: each test builds its own tiny table, so nothing depends on which seasons are
ingested locally.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from services.mlb_odds import coverage, market_lines, parse_total


def _db(tmp_path, rows):
    """rows: (game_id, season, team, venue, closing_odds, closing_total, closing_moneyline)"""
    p = tmp_path / "t.db"
    with sqlite3.connect(p) as c:
        c.execute("""CREATE TABLE mlb_box_team_games (game_id TEXT, season INT, team TEXT,
                     venue TEXT, closing_odds, closing_total, closing_moneyline)""")
        c.executemany("INSERT INTO mlb_box_team_games VALUES (?,?,?,?,?,?,?)", rows)
    return p


def test_the_2020_22_vintage_packs_a_total_and_a_moneyline_into_one_column(tmp_path):
    """The vendor puts the game total on one team's row and the favourite's moneyline on
    the other, in the same column — and not consistently home/road, so position cannot
    disambiguate it. Magnitude can: a baseball total is 4-20, a moneyline is |x| >= 100."""
    db = _db(tmp_path, [
        ("g1", 2022, "Milwaukee Brewers", "Road", -182.0, None, None),
        ("g1", 2022, "Chicago Cubs", "Home", 9.0, None, None),
    ])
    m = market_lines(db).set_index("team")
    assert m.loc["Milwaukee Brewers", "total"] == 9.0      # game-level, on both rows
    assert m.loc["Chicago Cubs", "total"] == 9.0
    assert m.loc["Milwaukee Brewers", "moneyline"] == -182.0
    assert m.loc["Milwaukee Brewers", "is_favourite"]
    # Only the favourite is priced in this vintage; inventing the dog's number would be
    # publishing a figure the vendor never did.
    assert m.loc["Chicago Cubs", "moneyline"] is None or pd.isna(m.loc["Chicago Cubs", "moneyline"])


def test_the_packed_column_is_not_home_road_consistent(tmp_path):
    """Real games from the feed: sometimes the road row holds the moneyline, sometimes the
    home row does. A positional rule would silently mislabel half the season."""
    db = _db(tmp_path, [
        ("g1", 2022, "Milwaukee Brewers", "Road", -182.0, None, None),   # ML on road row
        ("g1", 2022, "Chicago Cubs", "Home", 9.0, None, None),
        ("g2", 2022, "Pittsburgh Pirates", "Road", 8.0, None, None),      # ML on home row
        ("g2", 2022, "St. Louis Cardinals", "Home", -160.0, None, None),
    ])
    m = market_lines(db).set_index(["game_id", "team"])
    assert m.loc[("g1", "Milwaukee Brewers"), "is_favourite"]
    assert m.loc[("g2", "St. Louis Cardinals"), "is_favourite"]
    assert m.loc[("g1", "Chicago Cubs"), "total"] == 9.0
    assert m.loc[("g2", "Pittsburgh Pirates"), "total"] == 8.0


def test_the_2023_vintage_prices_both_sides(tmp_path):
    """A different, richer layout: per-team moneylines and a total carrying its juice."""
    db = _db(tmp_path, [
        ("g1", 2023, "Arizona Diamondbacks", "Road", None, "o7.5 even", 146.0),
        ("g1", 2023, "Los Angeles Dodgers", "Home", None, "u7.5 -122", -174.0),
    ])
    m = market_lines(db).set_index("team")
    assert m.loc["Arizona Diamondbacks", "total"] == 7.5
    assert m.loc["Los Angeles Dodgers", "total"] == 7.5
    assert m.loc["Arizona Diamondbacks", "moneyline"] == 146.0
    assert m.loc["Los Angeles Dodgers", "is_favourite"]
    assert not m.loc["Arizona Diamondbacks", "is_favourite"]


@pytest.mark.parametrize("raw,expected", [
    ("o7.5 -122", 7.5), ("u9.5", 9.5), ("o7.5 even", 7.5), ("8", 8.0), (9.0, 9.0),
    (-182.0, None),          # a moneyline is not a total
    ("", None), (None, None), ("garbage", None),
    (2.0, None), (25.0, None),   # outside any plausible baseball total
])
def test_total_parsing_accepts_both_vintages_and_refuses_nonsense(raw, expected):
    assert parse_total(raw) == expected


def test_an_underdog_only_row_does_not_become_a_favourite(tmp_path):
    """`is_favourite` must mean "priced as the favourite", not merely "has a number"."""
    db = _db(tmp_path, [
        ("g1", 2023, "A", "Road", None, "o8", 150.0),
        ("g1", 2023, "B", "Home", None, "u8", 120.0),      # both positive: no favourite
    ])
    m = market_lines(db)
    assert not m.is_favourite.any()


def test_missing_table_or_database_returns_empty_not_an_error(tmp_path):
    assert market_lines(tmp_path / "nope.db").empty
    blank = tmp_path / "blank.db"
    sqlite3.connect(blank).close()
    assert market_lines(blank).empty
    assert coverage(blank).empty


def test_coverage_counts_what_is_usable_per_season(tmp_path):
    db = _db(tmp_path, [
        ("g1", 2022, "A", "Road", -182.0, None, None),
        ("g1", 2022, "B", "Home", 9.0, None, None),
        ("g2", 2023, "C", "Road", None, "o7.5 even", 146.0),
        ("g2", 2023, "D", "Home", None, "u7.5 -122", -174.0),
    ])
    cov = coverage(db).set_index("season")
    assert cov.loc[2022, "games"] == 1 and cov.loc[2022, "with_total"] == 2
    assert cov.loc[2022, "with_moneyline"] == 1      # favourite only, honestly
    assert cov.loc[2023, "with_moneyline"] == 2      # both sides priced
