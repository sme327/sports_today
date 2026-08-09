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
_TEAM = [
    ["GAME INFO", None, None, None, "RUSHING", None, "PASSING", None],
    ["GAME-ID", "DATE", "WEEK#", "TEAM", "RUSH", "YDS", "COMP", "YDS"],
    ["g1", "2025-09-04", 1, "Dallas Cowboys", 25, 120, 21, 188],
    ["g1", "2025-09-04", 1, "Philadelphia Eagles", 30, 150, 24, 210],
    ["g2", "2026-01-11", 19, "Dallas Cowboys", 22, 95, 19, 240],
    ["g2", "2026-01-11", 19, "Philadelphia Eagles", 28, 130, 26, 205],
]

# Player feed: 3 header rows (super / sub / field), repeated YDS/TD across groups.
_PLAYER = [
    ["GAME & PLAYER INFORMATION", None, None, None, None, None, "OFFENSE", None, None, None],
    [None, None, None, None, None, None, "Passing", None, "Rushing", None],
    ["GAME-ID", "DATE", "WEEK #", "PLAYER ID", "PLAYER", "TEAM", "YDS", "TD", "YDS", "TD"],
    ["g1", "2025-09-04", 1, "dak-prescott", "Dak Prescott", "Dallas Cowboys", 188, 0, 32, 1],
    ["g1", "2025-09-04", 1, "jalen-hurts", "Jalen Hurts", "Philadelphia Eagles", 210, 2, 45, 0],
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
