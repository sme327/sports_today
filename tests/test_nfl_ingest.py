"""Offline tests for the NFL feed ingest — synthetic multi-row-header workbooks
(no real feed, no network). Covers the header flattening (unique names across
repeated fields), numeric coercion, season-type + opponent derivation."""

from __future__ import annotations

import sqlite3

import openpyxl

from src.nfl_ingest import import_nfl_feeds, read_player_feed, read_team_feed


def _write(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DATA"
    for r in rows:
        ws.append(r)
    teams = wb.create_sheet("TEAMS")
    teams.append(["BIGDATABALL\nINITIAL", "NFL.com\nINITIAL", "TEAM\nLONG NAME",
                  "TEAM\nSHORT NAME", "TEAM\nNICK NAME", "DIVISION", "CONFERENCE"])
    teams.append(["DAL", "DAL", "Dallas Cowboys", "Dallas", "Cowboys", "NFC East", "NFC"])
    teams.append(["PHI", "PHI", "Philadelphia Eagles", "Philadelphia", "Eagles", "NFC East", "NFC"])
    wb.save(path)


# Team feed: 2 header rows (category / field), repeated YDS under RUSHING + PASSING.
# Carries every column in REQUIRED_TEAM_COLUMNS — a fixture that omits them is not a
# realistic feed, and the drift guard is entitled to reject it.
_TEAM = [
    ["GAME INFO", None, None, None, None, None, "1 DOWNS", "TOTAL PLAYS",
     "RUSHING", None, "PASSING", None],
    ["GAME-ID", "DATE", "WEEK#", "TEAM", "VENUE", "FINAL", "FIRST DOWNS", "TOTAL PLAYS",
     "RUSH", "YDS", "COMP", "YDS"],
    ["g1", "2025-09-04", 1, "Dallas Cowboys", "Road", 17, 18, 62, 25, 120, 21, 188],
    ["g1", "2025-09-04", 1, "Philadelphia Eagles", "Home", 24, 21, 65, 30, 150, 24, 210],
    ["g2", "2026-01-11", 19, "Dallas Cowboys", "Home", 27, 20, 61, 22, 95, 19, 240],
    ["g2", "2026-01-11", 19, "Philadelphia Eagles", "Road", 20, 19, 63, 28, 130, 26, 205],
]

# Player feed: 3 header rows (super / sub / field), repeated YDS/TD across groups.
_PLAYER = [
    ["GAME & PLAYER INFORMATION", None, None, None, None, None, None, None, None,
     "OFFENSE", None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, None,
     "Passing", None, "Rushing", None, None, "Receiving", None],
    ["GAME-ID", "DATE", "WEEK #", "PLAYER ID", "PLAYER", "POSITION", "TEAM", "OPPONENT",
     "VENUE", "YDS", "TD", "YDS", "TD", "ATT", "YDS", "REC"],
    ["g1", "2025-09-04", 1, "dak-prescott", "Dak Prescott", "QB", "Dallas Cowboys",
     "Philadelphia Eagles", "Road", 188, 0, 32, 1, 4, 0, 0],
    ["g1", "2025-09-04", 1, "jalen-hurts", "Jalen Hurts", "QB", "Philadelphia Eagles",
     "Dallas Cowboys", "Home", 210, 2, 45, 0, 7, 0, 0],
]


def test_team_feed_flattens_and_pairs_opponents(tmp_path):
    p = tmp_path / "team.xlsx"
    _write(p, _TEAM)
    df = read_team_feed(p)
    assert "rushing_yds" in df.columns and "passing_yds" in df.columns   # repeated YDS disambiguated
    assert "game_date" in df.columns
    dal = df[(df.game_id == "g1") & (df.team == "Dallas Cowboys")].iloc[0]
    assert dal.rushing_yds == 120 and dal.passing_yds == 188
    assert dal.opponent == "Philadelphia Eagles"                          # paired
    assert dal.season_type == "regular"                                   # week 1
    assert df[df.week == 19].iloc[0].season_type == "postseason"          # wild card


def test_player_feed_unique_names_and_types(tmp_path):
    p = tmp_path / "player.xlsx"
    _write(p, _PLAYER)
    df = read_player_feed(p)
    assert {"passing_yds", "passing_td", "rushing_yds", "rushing_td"} <= set(df.columns)
    dak = df[df.player == "Dak Prescott"].iloc[0]
    assert dak.passing_yds == 188 and dak.rushing_yds == 32 and dak.passing_td == 0


def _reyear(rows, year):
    """Copy feed rows, shifting every YYYY- date by (year - 2025) so the whole feed —
    including the January playoff date — lands in one other season."""
    delta = year - 2025
    def shift(c):
        if isinstance(c, str) and len(c) >= 5 and c[:4].isdigit() and c[4] == "-":
            return f"{int(c[:4]) + delta}{c[4:]}"
        return c
    return [[shift(c) for c in r] for r in rows]


def test_multi_season_is_additive(tmp_path):
    db = tmp_path / "nfl.db"
    t25, p25 = tmp_path / "t25.xlsx", tmp_path / "p25.xlsx"
    _write(t25, _TEAM)
    _write(p25, _PLAYER)
    import_nfl_feeds(t25, p25, db)                       # season 2025

    t24, p24 = tmp_path / "t24.xlsx", tmp_path / "p24.xlsx"
    _write(t24, _reyear(_TEAM, 2024))
    _write(p24, _reyear(_PLAYER, 2024))
    import_nfl_feeds(t24, p24, db)                       # season 2024 — must keep 2025

    with sqlite3.connect(db) as conn:
        seasons = [r[0] for r in conn.execute(
            "SELECT DISTINCT season FROM nfl_team_games ORDER BY season")]
        total = conn.execute("SELECT COUNT(*) FROM nfl_team_games").fetchone()[0]
    assert seasons == [2024, 2025] and total == 8    # both seasons coexist (4 rows each)

    import_nfl_feeds(t25, p25, db)                       # re-load 2025 → replaces only 2025
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM nfl_team_games").fetchone()[0] == 8


def test_import_writes_all_tables(tmp_path):
    tp, pp, db = tmp_path / "t.xlsx", tmp_path / "p.xlsx", tmp_path / "nfl.db"
    _write(tp, _TEAM)
    _write(pp, _PLAYER)
    counts = import_nfl_feeds(tp, pp, db)
    assert counts["team_games"] == 4 and counts["player_games"] == 2
    assert counts["games"] == 2 and counts["weeks"] == 19 and counts["teams"] == 2
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM nfl_team_games").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM nfl_player_games").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM nfl_teams").fetchone()[0] == 2


# --- schema-drift guard (2026-08-11) -----------------------------------------------

def test_a_renamed_vendor_column_fails_loudly_instead_of_landing_silently(tmp_path):
    """The flattener derives names from whatever headers the workbook carries, so a
    renamed category yields a renamed *column* rather than an error — the drift is
    invisible until a matchup page breaks months later. The contract names what we
    actually depend on so the import refuses instead."""
    import pytest
    from src.nfl_ingest import REQUIRED_TEAM_COLUMNS, read_team_feed
    drifted = [list(r) for r in _TEAM]
    drifted[1][5] = "FINAL SCORE"          # vendor renames FINAL -> FINAL SCORE
    path = tmp_path / "drift.xlsx"
    _write(path, drifted)
    with pytest.raises(ValueError) as exc:
        read_team_feed(path)
    msg = str(exc.value)
    assert "final" in msg                   # names the column that vanished
    assert "drift.xlsx" in msg              # and the file it came from
    assert "final" in REQUIRED_TEAM_COLUMNS


def test_the_guard_names_every_missing_column_not_just_the_first(tmp_path):
    """A layout change usually moves several columns at once; reporting one at a time
    turns one investigation into five."""
    import pytest
    from src.nfl_ingest import read_player_feed
    drifted = [list(r) for r in _PLAYER]
    drifted[2][5] = "POS."                  # POSITION -> POS.
    drifted[2][7] = "OPP"                   # OPPONENT -> OPP
    path = tmp_path / "drift2.xlsx"
    _write(path, drifted)
    with pytest.raises(ValueError) as exc:
        read_player_feed(path)
    msg = str(exc.value)
    assert "opponent" in msg and "position" in msg
    assert "2 required" in msg


def test_a_faithful_feed_passes_the_guard(tmp_path):
    """The guard must not be so strict that a real feed trips it — the 2023-2025 seasons
    load clean, and these fixtures mirror their layout."""
    from src.nfl_ingest import read_player_feed, read_team_feed
    tp, pp = tmp_path / "t.xlsx", tmp_path / "p.xlsx"
    _write(tp, _TEAM)
    _write(pp, _PLAYER)
    assert not read_team_feed(tp).empty
    assert not read_player_feed(pp).empty
