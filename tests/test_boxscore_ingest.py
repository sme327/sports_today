"""Box-score ingest: header shapes, season calendars, and refusing to lose data.

Fixtures are built here rather than read from disk so the suite stays offline and does
not depend on a 65MB workbook in iCloud.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from src.boxscore_ingest import (SPORTS, add_season, import_feed, pick_sheet,
                                 read_feed)


def _write(path, sheets: dict[str, list[list]]):
    with pd.ExcelWriter(path) as xl:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(xl, sheet_name=name, index=False, header=False)
    return path


def _single_row_player(tmp_path, name="feed.xlsx", sheet="NBA-2025-26-PLAYER"):
    return _write(tmp_path / name, {sheet: [
        ["BIGDATABALL\nDATASET", "GAME-ID", "DATE", "PLAYER-ID", "PLAYER \nFULL NAME",
         "OWN \nTEAM", "OPPONENT \nTEAM", "VENUE\n(R/H/N)", "MIN", "PTS"],
        ["NBA 2025-2026", "G1", "2025-10-21", "201939", "Stephen Curry",
         "Golden State", "Los Angeles", "R", 34.5, 28],
        ["NBA 2025-2026", "G1", "2025-10-21", "203507", "Giannis A",
         "Los Angeles", "Golden State", "H", 33.0, 31],
    ], "METADATA": [["ignore me"]]})


def test_reads_the_single_row_header_layout(tmp_path):
    df = read_feed(_single_row_player(tmp_path), "player", sport=SPORTS["nba"])
    assert list(df["game_id"]) == ["G1", "G1"]
    assert list(df["player"]) == ["Stephen Curry", "Giannis A"]
    # Vintage-specific spellings collapse to one name, or a query cannot span files.
    assert {"team", "opponent", "venue"} <= set(df.columns)
    assert df["pts"].tolist() == [28, 31]


def test_reads_the_two_row_banner_layout(tmp_path):
    """A merged category row above the fields, so `AB` becomes `bat_ab` — while the banner
    section itself ("PLAYER INFORMATION") adds no prefix."""
    path = _write(tmp_path / "mlb.xlsx", {"2022-MLB-PLAYER": [
        ["PLAYER INFORMATION", None, None, None, None, "BATTING", None],
        ["BIGDATABALL\nDATASET", "GAME-ID", "DATE", "PLAYER", "TEAM", "AB", "H"],
        ["MLB 2022", "44658-MIL@CHC-1", "2022-04-07", "Kolten Wong", "Milwaukee", 5, 1],
    ]})
    df = read_feed(path, "player", sport=SPORTS["mlb"])
    assert "bat_ab" in df.columns and "bat_h" in df.columns
    assert "team" in df.columns          # banner section contributes no prefix
    assert df["bat_ab"].tolist() == [5]


def test_bare_numbered_periods_are_named_for_the_sport(tmp_path):
    """Period headers arrive as a mix of ints and floats, cleaning to `6` beside `1_0`.
    Unfixed, one table carries two spellings for the same concept — and calling a
    baseball inning `q1` (as the NFL map does) would be wrong outright."""
    path = _write(tmp_path / "mlbteam.xlsx", {"2020-MLB-TEAM": [
        ["GAME INFORMATION", None, None, None, None, None],
        ["DATASET", "GAME-ID", "DATE", "TEAM", 1.0, 6],
        ["MLB 2020", "g", "2020-07-23", "San Francisco", 0, 2],
    ]})
    df = read_feed(path, "team", sport=SPORTS["mlb"])
    assert "inning_1" in df.columns and "inning_6" in df.columns
    assert not any(c in df.columns for c in ("1_0", "6", "q1"))


@pytest.mark.parametrize("sport_key,date,expected", [
    # Autumn-to-spring: a June game belongs to the season that began the previous autumn.
    ("nba", "2025-06-13", 2024),
    ("nba", "2025-10-21", 2025),
    ("cbb", "2026-04-02", 2025),
    # Spring-to-autumn: the season is simply the year it is played in.
    ("mlb", "2022-11-05", 2022),
    ("wnba", "2025-07-22", 2025),
])
def test_season_follows_each_sports_own_calendar(sport_key, date, expected):
    df = pd.DataFrame({"game_date": [date]})
    assert add_season(df, SPORTS[sport_key])["season"].iloc[0] == expected


def test_covid_shifted_nba_season_still_groups_as_one_year():
    """2020-21 ran December to July. A naive "before September" rule still files the whole
    thing under 2020 — this pins that, because the alternative splits one season in two."""
    df = pd.DataFrame({"game_date": ["2020-12-22", "2021-07-03"]})
    assert add_season(df, SPORTS["nba"])["season"].tolist() == [2020, 2020]


def test_picks_the_right_sheet_despite_metadata_sheets_saying_team(tmp_path):
    path = _write(tmp_path / "w.xlsx", {
        "Team Data": [["DATASET", "GAME-ID", "DATE", "TEAM"], ["x", "g", "2025-05-16", "Dream"]],
        "Player Data": [["DATASET", "GAME-ID", "DATE", "Player Name"], ["x", "g", "2025-05-16", "A"]],
        "Teams": [["ignore"]], "Team Metadata": [["ignore"]]})
    assert pick_sheet(path, "team") == "Team Data"
    assert pick_sheet(path, "player") == "Player Data"


def test_dnp_sheet_is_not_mistaken_for_the_player_sheet(tmp_path):
    path = _write(tmp_path / "n.xlsx", {
        "NBA-PLAYER": [["DATASET", "GAME-ID", "DATE", "PLAYER \nFULL NAME"],
                       ["x", "g", "2025-10-21", "A"]],
        "DNP-DND-NWT": [["GAME DATE", "GAME-ID", "PLAYER NAME", "REASON"],
                        ["2025-10-21", "g", "B", "rest"]]})
    assert pick_sheet(path, "player") == "NBA-PLAYER"
    assert pick_sheet(path, "dnp") == "DNP-DND-NWT"


def test_a_thinner_file_does_not_silently_delete_a_fuller_season(tmp_path):
    """The bug this guard exists for: the 2024-25 NBA feed (pulled 28 May, 1,312 games)
    overwrote the archive's same season (pulled 8 June, 1,339 games) and took the Finals
    with it. Recency is not completeness."""
    db = tmp_path / "t.db"
    full = _write(tmp_path / "full.xlsx", {"P": [
        ["DATASET", "GAME-ID", "DATE", "PLAYER \nFULL NAME", "PTS"],
        ["x", "g1", "2025-10-21", "A", 10],
        ["x", "g2", "2025-10-22", "B", 12],
        ["x", "g3", "2025-10-23", "C", 14]]})
    thin = _write(tmp_path / "thin.xlsx", {"P": [
        ["DATASET", "GAME-ID", "DATE", "PLAYER \nFULL NAME", "PTS"],
        ["x", "g1", "2025-10-21", "A", 99]]})

    import_feed(full, "nba", "player", db)
    r = import_feed(thin, "nba", "player", db)
    assert r["skipped"] == {2025: (3, 1)}

    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT COUNT(DISTINCT game_id), SUM(pts) FROM nba_player_games").fetchone()
    assert rows == (3, 36)          # untouched: the thin file's 99 never landed

    forced = import_feed(thin, "nba", "player", db, force=True)
    assert forced["skipped"] == {}
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM nba_player_games").fetchone()[0] == 1


def test_loading_one_season_leaves_the_others_alone(tmp_path):
    db = tmp_path / "t.db"
    a = _write(tmp_path / "a.xlsx", {"P": [
        ["DATASET", "GAME-ID", "DATE", "PLAYER \nFULL NAME"], ["x", "g1", "2024-10-22", "A"]]})
    b = _write(tmp_path / "b.xlsx", {"P": [
        ["DATASET", "GAME-ID", "DATE", "PLAYER \nFULL NAME"], ["x", "g2", "2025-10-21", "B"]]})
    import_feed(a, "nba", "player", db)
    import_feed(b, "nba", "player", db)
    with sqlite3.connect(db) as conn:
        seasons = [r[0] for r in conn.execute(
            "SELECT DISTINCT season FROM nba_player_games ORDER BY season")]
    assert seasons == [2024, 2025]


def test_a_feed_without_game_ids_is_stored_but_flagged(tmp_path):
    """The 2020 WNBA vintage ships names and no ids. The project rule is to never join on
    names, so such rows must not look usable just because they loaded."""
    path = _write(tmp_path / "old.xlsx", {"WNBA-PLAYER-FEED": [
        ["DATASET", "DATE", "PLAYER FULL NAME", "OWN TEAM", "OPP TEAM", "PTS"],
        ["WNBA 2020", "2020-07-25", "A Player", "Storm", "Liberty", 20]]})
    r = import_feed(path, "wnba", "player", tmp_path / "t.db")
    assert r["joinable"] is False
    assert r["rows"] == 1
    df = read_feed(path, "player", sport=SPORTS["wnba"])
    assert "opponent" in df.columns and df["opponent"].iloc[0] == "Liberty"


def test_a_sheet_with_no_usable_date_is_refused(tmp_path):
    """Rows we cannot place in time cannot be filed under a season, and a seasonless
    table is worse than no table — so this fails loudly rather than loading."""
    path = _write(tmp_path / "bad.xlsx", {"P": [
        ["DATASET", "GAME-ID", "PLAYER \nFULL NAME"], ["x", "g", "A"]]})
    with pytest.raises(KeyError, match="no date column"):
        read_feed(path, "player", sport=SPORTS["nba"])


def test_unknown_sport_is_refused():
    with pytest.raises(ValueError, match="Unknown sport"):
        import_feed("x.xlsx", "nhl", "player")


def test_the_same_field_gets_one_name_across_feed_vintages(tmp_path):
    """The vendor writes `BATTING/H` one year and `Bat H` the next. Unreconciled they land
    in two columns with no overlap, so 2020-22 MLB hits sat in `bat_h` and 2023-24 in
    `batting_h` — a query on either silently returned half the history."""
    banner = _write(tmp_path / "old.xlsx", {"P": [
        ["PLAYER INFORMATION", None, None, "BATTING"],
        ["DATASET", "GAME-ID", "DATE", "H"],
        ["MLB 2022", "g1", "2022-04-07", 2]]})
    flat = _write(tmp_path / "new.xlsx", {"P": [
        ["DATASET", "GAME-ID", "DATE", "Bat H"],
        ["MLB 2023", "g2", "2023-04-07", 3]]})
    a = read_feed(banner, "player", sport=SPORTS["mlb"])
    b = read_feed(flat, "player", sport=SPORTS["mlb"])
    assert "bat_h" in a.columns and "bat_h" in b.columns
    assert "batting_h" not in a.columns

    db = tmp_path / "t.db"
    import_feed(banner, "mlb", "player", db)
    import_feed(flat, "mlb", "player", db)
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM mlb_box_player_games WHERE bat_h IS NOT NULL").fetchone()[0]
    assert rows == 2, "both vintages must land in the same column"


def test_text_columns_survive_even_when_nobody_listed_them(tmp_path):
    """Coercing everything unlisted to numeric nulled batter handedness — "L"/"R" parses
    as nothing — silently deleting the one column platoon splits need. Type is decided by
    what a column contains, not by whether someone remembered to enumerate it."""
    path = _write(tmp_path / "h.xlsx", {"P": [
        ["DATASET", "GAME-ID", "DATE", "PLAYER", "Bat HAND", "Bat H", "TEMPERATURE"],
        ["MLB 2022", "g1", "2022-04-07", "A", "L", 2, "72 degrees, clear"],
        ["MLB 2022", "g1", "2022-04-07", "B", "R", 1, "68 degrees, cloudy"]]})
    df = read_feed(path, "player", sport=SPORTS["mlb"])
    assert df["bat_hand"].tolist() == ["L", "R"]
    assert df["temperature"].notna().all()
    assert df["bat_h"].tolist() == [2, 1]      # genuinely numeric columns still coerce
