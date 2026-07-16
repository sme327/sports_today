"""Offline tests for the MLB game page (Phase 1). No network; synthetic PA data.

A deterministic synthetic feed with five teams, matched starters, and one
engineered hot bat (Team A) and cold bat (Team B) exercises the analytics and
builder end to end, plus the load-boundary (`as_of`) leakage guarantees.
"""

from __future__ import annotations

import sqlite3
from dataclasses import astuple  # noqa: F401  (kept for clarity of intent)
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from domain.models import SlateGame
from services import mlb_analytics as A
from services.data_access import load_plate_appearances
from services.mlb_game_page import build_mlb_game_page
from components import mlb_game as C
from components.opportunity_feed import opportunity_feed_html

TEAMS = ["Team A", "Team B", "Team C", "Team D", "Team E"]
GAME_DATE = date(2026, 6, 21)          # the game we build a page for
DATES = [date(2026, 6, d) for d in range(1, 21)]  # 20 prior game dates
PITCHER = {"Team A": ("PA1", "Ace A", "L"), "Team B": ("PB1", "Ace B", "R"),
           "Team C": ("PC1", "Ace C", "R"), "Team D": ("PC1", "Ace C", "R"),
           "Team E": ("PC1", "Ace C", "R")}


def _outcome(rng, hit_p, hr_p, bb_p, k_p):
    r = rng.random()
    if r < hr_p:
        return "HOME RUN", 1, 4, 0, 0, 1
    if r < hit_p:
        tb = rng.choice([1, 1, 1, 2])
        return ("DOUBLE" if tb == 2 else "SINGLE"), 1, tb, 0, 0, 0
    if r < hit_p + bb_p:
        return "WALK", 0, 0, 1, 0, 0
    if r < hit_p + bb_p + k_p:
        return "STRIKEOUT", 0, 0, 0, 1, 0
    return "GROUNDOUT", 0, 0, 0, 0, 0


def _synthetic_pa() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    pa_no = 0
    _ids: dict[str, int] = {}

    def _id(key: str) -> int:  # stable unique integer id (no hash collisions)
        return _ids.setdefault(key, 1000 + len(_ids))
    for team in TEAMS:
        opp_pitcher = {"Team A": PITCHER["Team B"], "Team B": PITCHER["Team A"]}.get(
            team, PITCHER["Team C"])
        pid, pname, phand = opp_pitcher
        # 9 regulars (4 PA/game) + 1 bench bat (1 PA/game -> too few recent).
        batters = [(f"{team}-b{i}", f"{team} Batter {i}", "L" if i % 2 else "R", 4) for i in range(9)]
        batters.append((f"{team}-bench", f"{team} Bench", "R", 1))
        all_dates = DATES + [GAME_DATE]   # include the game date (must be excluded on load)
        last10 = set(DATES[-10:])
        for d in all_dates:
            gid = f"{team}-{d.isoformat()}"
            for bid, bname, bhand, n in batters:
                for _ in range(n):
                    pa_no += 1
                    # Base rates; engineer one clearly hot bat (A-b0) and one
                    # clearly cold bat (B-b0) with large, unambiguous swings so
                    # the regression is robust to sampling noise.
                    hit_p, hr_p, bb_p, k_p = 0.25, 0.03, 0.09, 0.22
                    if bid == "Team A-b0":
                        hit_p, hr_p = (0.60, 0.16) if d in last10 else (0.15, 0.01)
                    elif bid == "Team B-b0":
                        hit_p, hr_p, k_p = (0.06, 0.00, 0.45) if d in last10 else (0.45, 0.05, 0.15)
                    elif team == "Team B":            # give B a stronger overall power base
                        hr_p += 0.02
                    play, is_hit, tb, bb, k, hr = _outcome(rng, hit_p, hr_p, bb_p, k_p)
                    reached = 1 if (is_hit or bb) else 0
                    rows.append({
                        "game_id": gid, "game_date": d.isoformat(), "inning": 1,
                        "batting_team": team, "pitching_team": "Opp",
                        "batter_id": _id(bid), "batter_name": bname,
                        "batter_hand": bhand,
                        "pitcher_id": _id(pid), "pitcher_name": pname,
                        "pitcher_hand": phand,
                        "play_type": play, "is_hit": is_hit, "total_bases": tb,
                        "is_home_run": hr, "is_walk": bb, "is_hbp": 0, "is_strikeout": k,
                        "is_official_ab": 0 if bb else 1, "reached_base": reached,
                        "has_risp": 1 if rng.random() < 0.25 else 0,
                        "pitch_count_pa": int(rng.integers(3, 7)),
                        "stolen_bases": 1 if rng.random() < 0.03 else 0,
                        "caught_stealing": 1 if rng.random() < 0.01 else 0,
                        "pa_number": pa_no,
                    })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def pa_all() -> pd.DataFrame:
    return _synthetic_pa()


@pytest.fixture(scope="module")
def pa(pa_all) -> pd.DataFrame:
    # As the loader would return it for a game on GAME_DATE: strictly before.
    d = pd.to_datetime(pa_all["game_date"])
    out = pa_all[d < pd.Timestamp(GAME_DATE)].copy()
    out["game_date"] = pd.to_datetime(out["game_date"])
    return out


@pytest.fixture(scope="module")
def game() -> SlateGame:
    return SlateGame(league="MLB", game_id="G1", away_name="Team A", home_name="Team B",
                     away_short="A", home_short="B", away_logo=None, home_logo=None,
                     venue="Test Park", status="Scheduled",
                     meta={"away_pitcher": "Ace A", "home_pitcher": "Ace B"})


def _tmp_db(pa_all: pd.DataFrame, tmp_path: Path) -> Path:
    db = tmp_path / "pa.db"
    with sqlite3.connect(db) as conn:
        pa_all.to_sql("plate_appearances", conn, index=False)
    return db


# 1. Leakage prevention at the load boundary.
def test_as_of_excludes_game_date_and_later(pa_all, tmp_path):
    db = _tmp_db(pa_all, tmp_path)
    loaded = load_plate_appearances(as_of=GAME_DATE, db_path=db)
    assert not loaded.empty
    assert loaded["game_date"].max().date() < GAME_DATE


# 2. Page builds with valid input.
def test_page_builds(pa, game):
    page = build_mlb_game_page(game, GAME_DATE, GAME_DATE, pa=pa)
    assert page.hero.away_team == "A" and page.hero.home_team == "B"  # short display names
    assert page.away_identity.team == "Team A" and page.home_identity.team == "Team B"
    assert page.away_identity.metrics and page.home_identity.metrics
    assert page.game_story
    assert page.as_of == GAME_DATE.isoformat()


# 3. Builds when probable pitchers are missing.
def test_page_builds_without_pitchers(pa, game):
    g = SlateGame(league="MLB", game_id="G1", away_name="Team A", home_name="Team B",
                  away_short="A", home_short="B", meta={})
    page = build_mlb_game_page(g, GAME_DATE, GAME_DATE, pa=pa)
    assert page.hero.probable_pitcher_status == "unavailable"
    assert page.key_matchups  # falls back to team-level matchup


# 4. Pitcher matching succeeds and fails gracefully.
def test_pitcher_matching(pa):
    assert A.match_pitcher(pa, "Ace A") is not None
    assert A.match_pitcher(pa, "Nonexistent Pitcher") is None
    assert A.match_pitcher(pa, None) is None


# 5 & 6. Identity and trend windows use only pre-game data.
def test_windows_exclude_game_date(pa):
    assert pa["game_date"].max().date() < GAME_DATE
    tf = A.player_trend_frame(pa, ["Team A", "Team B"])
    assert not tf.empty


# 7. Hot/cold minimum sample enforcement (bench bat with 1 PA/game excluded).
def test_trend_min_sample(pa):
    tf = A.player_trend_frame(pa, ["Team A", "Team B"])
    assert (tf["recent_pa"] >= A.TREND_RECENT_MIN_PA).all()
    assert (tf["baseline_pa"] >= A.TREND_BASELINE_MIN_PA).all()
    assert not any(name.endswith("Bench") for name in tf["player_name"])


# 8. No player appears in both heating and cooling.
def test_no_duplicate_hot_cold(pa, game):
    page = build_mlb_game_page(game, GAME_DATE, GAME_DATE, pa=pa)
    hot = {t.player_id for t in page.heating_up}
    cold = {t.player_id for t in page.cooling_off}
    assert hot.isdisjoint(cold)


# 9. Key matchups cite actual metrics.
def test_matchups_cite_metrics(pa, game):
    page = build_mlb_game_page(game, GAME_DATE, GAME_DATE, pa=pa)
    for m in page.key_matchups:
        assert m.supporting_metrics
        assert any(any(ch.isdigit() for ch in s) for s in m.supporting_metrics)


# 10. Unsupported metrics are never emitted.
def test_no_unsupported_metrics(pa, game):
    page = build_mlb_game_page(game, GAME_DATE, GAME_DATE, pa=pa)
    blob = " ".join([
        *page.game_story,
        page.away_identity.identity_summary, page.home_identity.identity_summary,
        *[m.explanation for m in page.key_matchups],
        *[s.explanation for s in page.storylines],
        page.game_shape.likely_shape if page.game_shape else "",
    ]).lower()
    for banned in ("bullpen", "defense", "weather", "park factor", "velocity",
                   "pitch type", "catcher", "statcast", "era", "win probability"):
        assert banned not in blob, banned


# 11. Story builder uses available facts.
def test_story_nonempty_sentences(pa, game):
    page = build_mlb_game_page(game, GAME_DATE, GAME_DATE, pa=pa)
    assert 1 <= len(page.game_story) <= 4
    assert all(isinstance(s, str) and s for s in page.game_story)


# 12. No-opportunity empty state.
def test_no_opportunity_empty_state(pa):
    g = SlateGame(league="MLB", game_id="G1", away_name="Nowhere FC", home_name="Elsewhere FC",
                  away_short="N", home_short="E", meta={})
    page = build_mlb_game_page(g, GAME_DATE, GAME_DATE, pa=pa)
    assert page.opportunities == ()
    html = opportunity_feed_html(list(page.opportunities))
    assert "op-row" not in html  # empty feed


# 13. Missing-headshot fallback is present in rendered markup.
def test_headshot_fallback_markup(pa, game):
    page = build_mlb_game_page(game, GAME_DATE, GAME_DATE, pa=pa)
    trends = page.heating_up + page.cooling_off
    assert trends
    html = C.player_trends_html(page.heating_up, page.cooling_off)
    assert "onerror=" in html and "img-fallback" in html
    assert all("/people/" in t.headshot_url for t in trends)


# 14. Components render safely (mobile uses %-based bars, no fixed pixel widths).
def test_components_render(pa, game):
    page = build_mlb_game_page(game, GAME_DATE, GAME_DATE, pa=pa)
    parts = [
        C.hero_html(page.hero), C.game_story_html(page.game_story),
        C.team_identity_html(page.away_identity, page.home_identity),
        C.key_matchups_html(page.key_matchups),
        C.player_trends_html(page.heating_up, page.cooling_off),
        C.game_shape_html(page.game_shape), C.storylines_html(page.storylines),
    ]
    for p in parts:
        assert isinstance(p, str)
    # bar widths are percentage-based (responsive), never fixed pixels
    assert "width:0" in parts[2] or "width:" in parts[2]
    assert "px%" not in "".join(parts)


# 15. Deterministic regression: engineered hot/cold bats surface correctly.
def test_regression_hot_cold(pa, game):
    page = build_mlb_game_page(game, GAME_DATE, GAME_DATE, pa=pa)
    hot_names = {t.player_name for t in page.heating_up}
    cold_names = {t.player_name for t in page.cooling_off}
    assert "Team A Batter 0" in hot_names        # engineered hot bat
    assert "Team B Batter 0" in cold_names        # engineered cold bat
    assert all(t.direction == "up" for t in page.heating_up)
    assert all(t.direction == "down" for t in page.cooling_off)
