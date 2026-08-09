"""Offline tests for the NFL matchup page builder + archive listing (synthetic DB)."""

from __future__ import annotations

import sqlite3

import pandas as pd

from services.nfl_game_page import build_nfl_game_page, list_games, list_weeks


def _row(gid, wk, team, opp, venue, pts, pyd, ryd):
    return {"game_id": gid, "game_date": f"2025-09-{wk:02d}", "week": wk,
            "season_type": "regular", "team": team, "opponent": opp, "venue": venue,
            "final": pts, "yards_total_yards": pyd + ryd, "passing_yds": pyd,
            "rushing_yds": ryd, "total_plays": 64, "passing_att": 32, "rushing_rush": 26,
            "passing_comp": 21, "turnovers_penalties_turnovers": 1,
            "third_downs_made": 6, "third_downs_att": 14, "first_downs": 21,
            "sacks_sacked": 2, "passing_int": 1}


def _seed(tmp_path):
    db = tmp_path / "nfl.db"
    rows = [
        # Weeks 1–2 give A and B prior form; week 3 is the game we preview.
        _row("g1", 1, "A", "B", "Road", 30, 300, 100), _row("g1", 1, "B", "A", "Home", 20, 250, 90),
        _row("g2", 2, "A", "C", "Home", 27, 280, 110), _row("g2", 2, "C", "A", "Road", 13, 210, 70),
        _row("g3", 2, "B", "C", "Home", 24, 240, 120), _row("g3", 2, "C", "B", "Road", 21, 260, 80),
        _row("g4", 3, "A", "B", "Road", 31, 290, 130), _row("g4", 3, "B", "A", "Home", 17, 200, 95),
    ]
    with sqlite3.connect(db) as conn:
        pd.DataFrame(rows).to_sql("nfl_team_games", conn, index=False)
    return db


def test_build_matchup_page(tmp_path):
    db = _seed(tmp_path)
    page = build_nfl_game_page("g4", db_path=db)
    assert page is not None
    h = page.hero
    assert h.away == "A" and h.home == "B"          # venue Road/Home
    assert h.away_score == 31 and h.home_score == 17 and h.winner == "away"
    assert h.away_record == "2-0" and h.home_record == "1-1"   # coming in (weeks 1–2)
    # identity + battlefields computed from prior games (leakage-safe)
    assert page.identity and page.battlefields
    assert page.away_form and "W W" in page.away_form.results
    assert "thin" in page.note                       # only 2 prior games (< 4) → small-sample note


def test_season_opener_has_no_prior_form(tmp_path):
    db = _seed(tmp_path)
    page = build_nfl_game_page("g1", db_path=db)   # week 1 → nothing before it
    assert page.hero.away_record == "0-0" and page.hero.home_record == "0-0"
    assert page.identity == () and page.battlefields == ()
    assert "opener" in page.note.lower()


def test_archive_listing(tmp_path):
    db = _seed(tmp_path)
    weeks = list_weeks(db_path=db)
    assert [w["week"] for w in weeks] == [1, 2, 3]
    assert next(w for w in weeks if w["week"] == 2)["games"] == 2
    g = list_games(3, db_path=db)
    assert len(g) == 1 and g[0]["away"] == "A" and g[0]["away_score"] == 31


def test_missing_game_returns_none(tmp_path):
    assert build_nfl_game_page("nope", db_path=_seed(tmp_path)) is None
