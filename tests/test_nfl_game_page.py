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
    assert page.thesis and any("offense" in s for s in page.thesis)   # synthesized read
    assert page.away_rest == 1 and page.home_rest == 1               # 09-03 minus 09-02


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


# --- player spotlights: the leakage-safe pick + its backtest ----------------

def _p(gid, wk, pid, name, pos, **stats):
    row = {"game_id": gid, "game_date": f"2025-09-{wk:02d}", "week": wk,
           "player_id": pid, "player": name, "position": pos, "team": "A", "opponent": "B",
           "passing_att": 0, "passing_yds": 0, "rushing_att": 0, "rushing_yds": 0,
           "receiving_tar": 0, "receiving_rec": 0, "receiving_yds": 0}
    row.update(stats)
    return row


def _seed_players(tmp_path):
    """Weeks 1–5 of prior form for three A players, then week 6 (`g6`) as the game
    being previewed. Chosen so the reachable bars land on 275 pass / 75 rush / 60 rec."""
    db = tmp_path / "nfl_players.db"
    team_rows = []
    for wk in range(1, 7):
        team_rows += [_row(f"g{wk}", wk, "A", "B", "Road", 24, 260, 100),
                      _row(f"g{wk}", wk, "B", "A", "Home", 20, 240, 90)]

    qb = [260, 275, 300, 240, 280]      # → 275 bar clears 3/5 = 60%
    rb = [80, 95, 60, 110, 70]          # → 75 bar clears 3/5 = 60%
    wr = [70, 55, 80, 45, 65]           # → 60 bar clears 3/5 = 60%
    player_rows = []
    for wk in range(1, 6):
        player_rows += [
            _p(f"g{wk}", wk, "a-qb", "A QB", "QB", passing_att=32, passing_yds=qb[wk - 1]),
            _p(f"g{wk}", wk, "a-rb", "A RB", "RB", rushing_att=15, rushing_yds=rb[wk - 1]),
            _p(f"g{wk}", wk, "a-wr", "A WR", "WR", receiving_tar=8, receiving_yds=wr[wk - 1]),
        ]
    # Week 6 — the previewed game. QB clears his bar, RB misses his, WR did not play.
    player_rows += [
        _p("g6", 6, "a-qb", "A QB", "QB", passing_att=38, passing_yds=310),
        _p("g6", 6, "a-rb", "A RB", "RB", rushing_att=11, rushing_yds=42),
    ]
    with sqlite3.connect(db) as conn:
        pd.DataFrame(team_rows).to_sql("nfl_team_games", conn, index=False)
        pd.DataFrame(player_rows).to_sql("nfl_player_games", conn, index=False)
    return db


def _spot(page, player):
    return next(s for s in page.away_spotlights if s.player == player)


def test_spotlight_backtests_the_pick_against_what_happened(tmp_path):
    page = build_nfl_game_page("g6", db_path=_seed_players(tmp_path))
    qb, rb = _spot(page, "A QB"), _spot(page, "A RB")
    assert qb.market == "275+ Pass Yards" and qb.actual == 310.0 and qb.result == "hit"
    assert rb.market == "75+ Rush Yards" and rb.actual == 42.0 and rb.result == "miss"


def test_spotlight_pick_uses_only_games_before_kickoff(tmp_path):
    """The 310-yard week-6 game must not feed the pick that is being backtested —
    otherwise the spotlight would be grading itself on its own answer."""
    page = build_nfl_game_page("g6", db_path=_seed_players(tmp_path))
    support = _spot(page, "A QB").support
    assert "(3/5)" in support           # five prior games, not six
    assert "271.0 avg" in support       # mean of weeks 1–5; leaking week 6 gives 277.5


def test_spotlight_is_honest_when_the_player_did_not_appear(tmp_path):
    page = build_nfl_game_page("g6", db_path=_seed_players(tmp_path))
    wr = _spot(page, "A WR")
    assert wr.market == "60+ Rec Yards"      # the pick is still shown
    assert wr.actual is None and wr.result is None   # …but never graded as a miss
