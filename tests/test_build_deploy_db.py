"""Building the slim deployment database.

Offline: each test builds its own SQLite file.
"""

from __future__ import annotations

import sqlite3

import pytest

from scripts.build_deploy_db import KEEP, _keep_set, build, report


def _db(tmp_path, tables):
    p = tmp_path / "src.db"
    with sqlite3.connect(p) as c:
        for name, rows in tables.items():
            c.execute(f'CREATE TABLE "{name}" (a INTEGER)')
            c.executemany(f'INSERT INTO "{name}" VALUES (?)', [(i,) for i in range(rows)])
    return p


def test_research_tables_are_dropped_and_app_tables_survive(tmp_path):
    src = _db(tmp_path, {"plate_appearances": 50, "opportunity_snapshots": 20,
                         "nfl_team_games": 10, "cbb_player_games": 500,
                         "nba_espn_player_logs": 400, "nhl_espn_player_logs": 300})
    out = build(src, tmp_path / "out.db")
    with sqlite3.connect(out) as c:
        left = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"plate_appearances", "opportunity_snapshots", "nfl_team_games"} <= left
    assert not {"cbb_player_games", "nba_espn_player_logs", "nhl_espn_player_logs"} & left


def test_the_graded_ledger_is_never_dropped():
    """Grading history is not reproducible — it records what was served on a given day.
    Losing it would destroy the only feedback loop the product has."""
    assert "opportunity_snapshots" in _keep_set()
    assert "game_outcomes" in _keep_set()


def test_it_is_an_allow_list_so_a_new_research_table_is_excluded_by_default(tmp_path):
    """The safe direction: shipping a table nobody reads costs bandwidth, while dropping
    one somebody does breaks a page. A table added later must not silently ride along."""
    src = _db(tmp_path, {"plate_appearances": 10, "some_future_research_table": 900})
    out = build(src, tmp_path / "out.db")
    with sqlite3.connect(out) as c:
        left = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "some_future_research_table" not in left


def test_the_file_actually_shrinks(tmp_path):
    """Dropping tables without VACUUM leaves the pages allocated and the file the same
    size on disk, which would make the whole exercise pointless."""
    src = _db(tmp_path, {"plate_appearances": 100, "cbb_player_games": 40_000})
    before = src.stat().st_size
    out = build(src, tmp_path / "out.db")
    assert out.stat().st_size < before * 0.6


def test_report_flags_a_missing_expected_table(tmp_path, capsys):
    """If a table the app needs has vanished from the source, deploying silently would
    ship a broken app. Report must fail instead."""
    src = _db(tmp_path, {"cbb_player_games": 10})      # nothing the app reads
    assert report(src) == 1


def test_every_keep_group_is_documented_with_a_reason():
    """The allow-list is read by whoever next wonders whether a table is safe to drop."""
    for group, tables in KEEP.items():
        assert group.strip(), "each group needs a human-readable reason"
        assert tables, f"{group} lists no tables"
