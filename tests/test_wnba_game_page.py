"""Offline tests for the WNBA matchup page. No network; synthetic box scores.

Four teams play a round of games so every game_id pairs two teams (required for
opponent aggregation). One engineered star (Team One, player 0) validates the
featured/role paths.
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from components import wnba_game as C
from domain.models import SlateGame
from services import wnba_analytics as A
from services.wnba_game_page import build_wnba_game_page

TEAMS = [("1", "Team One", "T1"), ("2", "Team Two", "T2"),
         ("3", "Team Three", "T3"), ("4", "Team Four", "T4")]
DATES = [date(2026, 6, d) for d in range(1, 13)]     # 12 game dates
GAME_DATE = date(2026, 6, 13)                          # the matchup we build


def _players(team_id, team, abbr):
    # 8 players: 5 starters (~30 min), 3 bench (~14 min). Player 0 is a star.
    out = []
    for i in range(8):
        starter = i < 5
        out.append((f"{abbr}-p{i}", f"{abbr} Player {i}", "G" if i < 2 else "F" if i < 5 else "C",
                    starter, team_id, team, abbr))
    return out


def _synthetic_logs() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    rows = []
    # Each date: game A = T1 vs T2, game B = T3 vs T4 (alternate home/away).
    pairings = [(TEAMS[0], TEAMS[1]), (TEAMS[2], TEAMS[3])]
    for gi, d in enumerate(DATES):
        for (home, away) in ([(a, b) if gi % 2 == 0 else (b, a) for (a, b) in pairings]):
            gid = f"{home[2]}{away[2]}-{d.isoformat()}"
            for side, opp, ha in ((home, away, "home"), (away, home, "away")):
                for pid, pname, pos, starter, tid, team, abbr in _players(*side):
                    mins = rng.normal(30 if starter else 14, 3)
                    star = (pid == "T1-p0")
                    base_pts = (24 if star else 12 if starter else 5)
                    if star and d in DATES[-5:]:
                        base_pts = 30
                    pts = max(0, rng.normal(base_pts, 4))
                    fga = max(1, pts / 1.1 + rng.normal(0, 2))
                    fgm = min(fga, max(0, pts / 2.1))
                    tpa = max(0, rng.normal(4 if pos == "G" else 1, 1))
                    tpm = min(tpa, max(0, tpa * 0.35))
                    reb = max(0, rng.normal(8 if pos == "C" else 4, 2))
                    ast = max(0, rng.normal(6 if star else 2, 1.5))
                    rows.append({
                        "game_id": gid, "game_date": d.isoformat() + "T23:00Z",
                        "season": 2026, "season_type": 2,
                        "player_id": pid, "player_name": pname, "short_name": pname,
                        "position": pos, "jersey": str(pid[-1]), "headshot": f"http://h/{pid}.png",
                        "team_id": tid, "team": team, "team_abbr": abbr,
                        "opponent_id": opp[0], "opponent": opp[1], "opponent_abbr": opp[2],
                        "home_away": ha, "started": int(starter), "active": 1,
                        "minutes": round(mins, 1), "field_goals_made": round(fgm),
                        "field_goals_attempted": round(fga),
                        "three_pointers_made": round(tpm), "three_pointers_attempted": round(tpa),
                        "free_throws_made": round(max(0, pts - 2 * fgm)),
                        "free_throws_attempted": round(max(0, pts - 2 * fgm) + 1),
                        "offensive_rebounds": round(reb * 0.3), "defensive_rebounds": round(reb * 0.7),
                        "rebounds": round(reb), "assists": round(ast),
                        "steals": round(max(0, rng.normal(1, .6))),
                        "blocks": round(max(0, rng.normal(1 if pos == "C" else .3, .5))),
                        "turnovers": round(max(0, rng.normal(2, 1))),
                        "personal_fouls": round(max(0, rng.normal(2, 1))),
                        "plus_minus": round(rng.normal(0, 8)), "points": round(pts),
                    })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def logs() -> pd.DataFrame:
    return _synthetic_logs()


@pytest.fixture(scope="module")
def game() -> SlateGame:
    return SlateGame(league="WNBA", game_id="G1", away_name="Team One", home_name="Team Two",
                     away_short="Team One", home_short="Team Two",
                     away_abbr="T1", home_abbr="T2", away_id="1", home_id="2",
                     venue="Test Arena", start_time=datetime(2026, 6, 13, 23, 0))


# ------------------------------------------------------------- analytics -----
def test_team_game_frame_pairs_opponent(logs):
    tg = A.team_game_frame(logs)
    assert not tg.empty
    assert (tg["pts_against"] == tg["opp_pts"]).all()
    assert set(tg["team_id"]) == {"1", "2", "3", "4"}


def test_team_season_percentiles_present(logs):
    tt = A.team_season_table(A.team_game_frame(logs))
    for col in ("off_pct", "def_pct", "three_pct", "reb_pct", "pace_pct"):
        assert col in tt.columns
        assert tt[col].between(0, 100).all()


def test_recent_form_and_streak(logs):
    tg = A.team_game_frame(logs)
    rf = A.recent_form(tg, "1")
    assert rf["last_n"] == 5
    assert set(rf["results"]) <= {"W", "L"}
    assert rf["streak"][0] in ("W", "L")


# --------------------------------------------------------------- page --------
def test_page_builds_all_sections(logs, game):
    p = build_wnba_game_page(game, GAME_DATE, GAME_DATE, logs=logs)
    assert p.hero.away_record and p.hero.home_record
    assert p.away_identity.metrics and p.home_identity.metrics
    assert p.game_script
    assert 3 <= len(p.battlefields) <= 5
    assert p.away_snapshot and p.home_snapshot
    assert p.away_trends and p.away_trends.sparks
    assert p.as_of == GAME_DATE.isoformat()


def test_featured_and_shape_use_star(logs, game):
    p = build_wnba_game_page(game, GAME_DATE, GAME_DATE, logs=logs)
    assert p.hero.away_featured is not None
    assert p.hero.away_featured.name == "T1 Player 0"     # engineered star
    shape_names = {s.name for s in p.shape_players}
    assert "T1 Player 0" in shape_names


def test_battlefields_cite_real_numbers(logs, game):
    p = build_wnba_game_page(game, GAME_DATE, GAME_DATE, logs=logs)
    for b in p.battlefields:
        assert b.supporting_metrics
        assert any(any(ch.isdigit() for ch in s) for s in b.supporting_metrics)
        assert b.advantage in (p.hero.away_team, p.hero.home_team, game.away_short, game.home_short, "Even")


def test_no_unsupported_claims(logs, game):
    p = build_wnba_game_page(game, GAME_DATE, GAME_DATE, logs=logs)
    blob = " ".join([
        *p.game_script, p.away_identity.summary, p.home_identity.summary,
        *[b.explanation for b in p.battlefields],
        *[s.why_tonight for s in p.shape_players],
    ]).lower()
    for banned in ("injury", "injured", "assignment", "defensive assignment",
                   "offensive rating", "defensive rating", "net rating", "betting", "odds"):
        assert banned not in blob, banned


def test_trends_no_overlap(logs, game):
    p = build_wnba_game_page(game, GAME_DATE, GAME_DATE, logs=logs)
    up = {t.player_id for t in p.trending_up}
    down = {t.player_id for t in p.trending_down}
    assert up.isdisjoint(down)


def test_empty_logs_returns_hero_only(game):
    p = build_wnba_game_page(game, GAME_DATE, GAME_DATE, logs=pd.DataFrame())
    assert p.hero is not None
    assert p.battlefields == () and p.shape_players == ()


def test_opportunities_reuse_scorer(logs, game):
    p = build_wnba_game_page(game, GAME_DATE, GAME_DATE, logs=logs)
    # WNBA opportunities use points/rebounds/assists markets from the shared scorer.
    if p.opportunities:
        assert all(o.league == "WNBA" for o in p.opportunities)
        assert all(o.market for o in p.opportunities)


# ------------------------------------------------------------- rendering -----
def test_components_render_and_sparkline(logs, game):
    p = build_wnba_game_page(game, GAME_DATE, GAME_DATE, logs=logs)
    parts = [
        C.hero_html(p.hero), C.game_script_html(p.game_script),
        C.snapshot_html(p.away_snapshot, p.home_snapshot, "Team One", "Team Two"),
        C.team_identity_html(p.away_identity, p.home_identity),
        C.battlefields_html(p.battlefields), C.shape_players_html(p.shape_players),
        C.trends_html(p.trending_up, p.trending_down),
        C.team_trends_html(p.away_trends, p.home_trends),
        C.opportunities_html(p.opportunities),
    ]
    joined = "".join(parts)
    assert all(isinstance(x, str) for x in parts)
    assert "<svg class=\"wnba-spark\"" in joined     # sparkline rendered
    assert "wnba-dot" in joined                       # W/L form dots
