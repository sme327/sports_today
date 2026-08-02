"""Offline tests for the MLS team-data integration (Phase 3B).

Covers provider parsing, collector validation/idempotency, leakage-safe repository
queries, the tactical-proxy engine (selection + wording honesty), storyline
triggers, and the builder's real-data path (via a synthetic frame). No network.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd
import pytest

from services import mls_analytics as A
from services import mls_repository as R
from services import mls_store
from src import espn_soccer as E
from src import mls_collector as MC


# ============================================================ provider parse ==
def _team_block(team_id, home, stats, drop=(), extra_zero=None):
    names = {
        "possessionPct": "55.0", "totalShots": "14", "shotsOnTarget": "6",
        "wonCorners": "7", "foulsCommitted": "10", "offsides": "2", "saves": "3",
        "yellowCards": "1", "redCards": "0", "totalPasses": "500",
        "accuratePasses": "440", "totalCrosses": "20", "accurateCrosses": "5",
        "totalTackles": "18", "interceptions": "9", "totalClearance": "22",
        "blockedShots": "4", "penaltyKickGoals": "0", "penaltyKickShots": "0",
    }
    for d in drop:
        names.pop(d, None)
    if extra_zero:
        names[extra_zero] = "0"
    stats_list = [{"name": k, "displayValue": v} for k, v in names.items()]
    return {"team": {"id": team_id}, "homeAway": "home" if home else "away",
            "statistics": stats_list}


def _summary(home_id="100", away_id="200", **kw):
    return {"boxscore": {"teams": [_team_block(home_id, True, {}, **kw),
                                   _team_block(away_id, False, {})]},
            "gameInfo": {"venue": {"id": "9", "fullName": "Test Park"},
                         "attendance": 12000,
                         "officials": [{"displayName": "Ref One",
                                        "position": {"name": "Referee"}}]}}


def test_parse_team_stats_counts_and_derivations():
    rows = E.parse_team_stats(_summary())
    assert len(rows) == 2
    home = next(r for r in rows if r["is_home"] == 1)
    assert home["total_shots"] == 14 and home["shots_on_target"] == 6
    assert home["shot_pct"] == pytest.approx(100 * 6 / 14, abs=0.1)     # derived, precise
    assert home["pass_pct"] == pytest.approx(100 * 440 / 500, abs=0.1)
    assert home["possession_pct"] == 55.0                                # provider percent
    assert home["opponent_id"] == "200"


def test_parse_team_stats_missing_optional_is_none_not_zero():
    rows = E.parse_team_stats(_summary(drop=("interceptions",)))
    assert rows[0]["interceptions"] is None                              # provider omission → None


def test_parse_team_stats_valid_zero_preserved():
    rows = E.parse_team_stats(_summary())
    home = next(r for r in rows if r["is_home"] == 1)
    assert home["red_cards"] == 0                                        # present '0' → 0, not None


def test_parse_team_stats_reordered_statistics_ok():
    payload = _summary()
    payload["boxscore"]["teams"][0]["statistics"].reverse()             # order must not matter
    rows = E.parse_team_stats(payload)
    home = next(r for r in rows if r["is_home"] == 1)
    assert home["total_shots"] == 14 and home["won_corners"] == 7


def test_parse_team_stats_invalid_structure_raises():
    with pytest.raises(ValueError):
        E.parse_team_stats({"boxscore": {"teams": []}})
    bad = _summary()
    bad["boxscore"]["teams"][0]["team"].pop("id")
    with pytest.raises(ValueError):
        E.parse_team_stats(bad)


def test_parse_standings():
    payload = {"children": [
        {"name": "Eastern Conference", "standings": {"entries": [
            {"team": {"id": "1"}, "stats": [
                {"name": "rank", "value": 1}, {"name": "points", "value": 30},
                {"name": "gamesPlayed", "value": 12}, {"name": "wins", "value": 9},
                {"name": "ties", "value": 3}, {"name": "losses", "value": 0},
                {"name": "pointsFor", "value": 22}, {"name": "pointsAgainst", "value": 8},
                {"name": "pointDifferential", "value": 14}]}]}}]}
    rows = E.parse_standings(payload)
    assert len(rows) == 1
    r = rows[0]
    assert r["team_id"] == "1" and r["conference"] == "Eastern Conference"
    assert r["conference_rank"] == 1 and r["goals_for"] == 22 and r["goal_difference"] == 14


def test_parse_match_meta():
    meta = E.parse_match_meta(_summary())
    assert meta["venue_id"] == "9" and meta["attendance"] == 12000 and meta["referee"] == "Ref One"


# ================================================================ collector ==
def test_collector_retries_then_succeeds():
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise __import__("requests").RequestException("boom")
        return "ok"
    assert MC._with_retries(flaky, retries=3, base_sleep=0) == "ok"
    assert calls["n"] == 3


def test_collector_validate_reconciliation_and_goals():
    event = {"game_id": "555", "home_id": "100", "away_id": "200",
             "home_score": 3, "away_score": 1, "game_date": "2026-04-01T00:00Z",
             "discovery_date": "2026-04-01", "season_year": 2026, "season_type": 13846,
             "state": "final", "venue": "X"}
    match, teams = MC.validate_and_build(event, _summary(), "t0")
    assert match["event_id"] == "555" and match["match_date"] == "2026-04-01"
    home = next(t for t in teams if t["is_home"] == 1)
    assert home["goals_for"] == 3 and home["goals_against"] == 1                 # injected from score
    away = next(t for t in teams if t["is_home"] == 0)
    assert away["goals_for"] == 1 and away["goals_against"] == 3


def test_collector_validate_id_mismatch_raises():
    event = {"game_id": "555", "home_id": "999", "away_id": "888",
             "home_score": 1, "away_score": 0, "discovery_date": "2026-04-01"}
    with pytest.raises(MC.MLSCollectorError):
        MC.validate_and_build(event, _summary(), "t0")   # boxscore ids 100/200 ≠ 999/888


def test_store_idempotent_upsert_and_dedup(tmp_path):
    db = tmp_path / "t.db"
    with sqlite3.connect(db) as conn:
        mls_store.ensure_tables(conn)
        rows = [{"event_id": "1", "team_id": "100"}, {"event_id": "1", "team_id": "200"}]
        mls_store.upsert_team_stats(conn, rows)
        mls_store.upsert_team_stats(conn, rows)          # second time must not duplicate
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM mls_team_match_stats").fetchone()[0]
        assert n == 2
        assert mls_store.collected_event_ids(conn) == {"1"}


# =============================================================== repository ==
def _seed_repo_db(tmp_path):
    """Two teams (H stronger) across 6 dated matches + standings."""
    db = tmp_path / "repo.db"
    matches, stats = [], []
    dates = ["2026-03-01", "2026-03-08", "2026-03-15", "2026-03-22", "2026-04-01", "2026-04-08"]
    for i, d in enumerate(dates):
        eid = f"E{i}"
        h_is_home = (i % 2 == 0)  # alternate venue for team H vs neutral opp O
        matches.append({"event_id": eid, "match_date": d, "home_team_id": "H" if h_is_home else "O",
                        "away_team_id": "O" if h_is_home else "H", "home_score": 2, "away_score": 0})
        # team H: 2 goals for, 0 against, 15 shots; team O: 0 for 2 against 8 shots
        stats.append({"event_id": eid, "team_id": "H", "opponent_id": "O",
                      "is_home": 1 if h_is_home else 0, "goals_for": 2, "goals_against": 0,
                      "total_shots": 15, "shots_on_target": 7, "possession_pct": 58.0,
                      "total_passes": 500, "accurate_passes": 450, "won_corners": 6,
                      "fouls_committed": 9, "yellow_cards": 1, "red_cards": 0,
                      "total_crosses": 18, "accurate_crosses": 5})
        stats.append({"event_id": eid, "team_id": "O", "opponent_id": "H",
                      "is_home": 0 if h_is_home else 1, "goals_for": 0, "goals_against": 2,
                      "total_shots": 8, "shots_on_target": 2, "possession_pct": 42.0,
                      "total_passes": 400, "accurate_passes": 330, "won_corners": 3,
                      "fouls_committed": 12, "yellow_cards": 2, "red_cards": 0,
                      "total_crosses": 12, "accurate_crosses": 2})
    with sqlite3.connect(db) as conn:
        mls_store.ensure_tables(conn)
        mls_store.upsert_matches(conn, matches)
        mls_store.upsert_team_stats(conn, stats)
        mls_store.upsert_standings(conn, [{"season": 2026, "team_id": "H", "snapshot_date": "2026-04-09",
                                           "conference": "Western Conference", "conference_rank": 1,
                                           "points": 18, "goal_difference": 12}])
        conn.commit()
    return db


def test_repository_is_leakage_safe_and_excludes_selected(tmp_path):
    db = _seed_repo_db(tmp_path)
    frame = R.team_match_frame(date(2026, 3, 22), exclude_event_id="E1", db_path=db)
    # strictly before 03-22 → E0,E1,E2 ... but E1 excluded and E3+ are on/after → only E0,E2
    assert set(frame["event_id"]) == {"E0", "E2"}
    assert (frame["match_date"] < "2026-03-22").all()


def test_repository_aggregates_and_splits(tmp_path):
    db = _seed_repo_db(tmp_path)
    frame = R.team_match_frame(date(2026, 5, 1), db_path=db)
    agg = R.team_aggregate(frame, "H")
    assert agg["matches"] == 6
    assert agg["goals_for"] == pytest.approx(2.0) and agg["goals_against"] == pytest.approx(0.0)
    assert agg["shot_accuracy"] == pytest.approx(100 * 7 / 15, abs=0.1)
    assert agg["shots_faced"] == pytest.approx(8.0)             # opponent shots merged
    home = R.team_aggregate(frame, "H", venue="home")
    away = R.team_aggregate(frame, "H", venue="away")
    assert home["matches"] == 3 and away["matches"] == 3
    assert home["ppm"] == 3.0                                   # H wins every match
    la = R.league_averages(frame)
    assert la["possession"] == pytest.approx(50.0)              # zero-sum sanity


def test_repository_last5_and_standings(tmp_path):
    db = _seed_repo_db(tmp_path)
    frame = R.team_match_frame(date(2026, 5, 1), db_path=db)
    r = R.recent_results(frame, "H", n=5)
    assert r["matches"] == 5 and r["form"] == ("W", "W", "W", "W", "W") and r["unbeaten"]
    sl = R.standings_lookup("H", date(2026, 5, 1), db_path=db)
    assert sl["conference_rank"] == 1 and sl["points"] == 18


# ================================================================ analytics ==
_STRONG = {"matches": 12, "possession": 58, "pass_completion": 86, "shots": 16,
           "corners": 6.5, "crosses": 20, "shot_accuracy": 42, "shots_faced": 9,
           "fouls": 9, "yellows": 1.4, "reds_total": 1, "goals_for": 1.8, "goals_against": 0.7}
_WEAK = {"matches": 12, "possession": 45, "pass_completion": 80, "shots": 10,
         "corners": 3.5, "crosses": 12, "shot_accuracy": 33, "shots_faced": 15,
         "fouls": 12, "yellows": 2.1, "reds_total": 3, "goals_for": 0.9, "goals_against": 1.7}

_BANNED = ["high press", "low block", "transition", "directness", "line height",
           "defensive line", "counterattack", "counter-attack", "game control",
           "dominate", "possession control", "build-up structure", "width"]


def test_proxy_dimensions_only_meaningful_and_nonredundant():
    dims = A.proxy_dimensions(_STRONG, _WEAK, home_name="H", away_name="A")
    assert 1 <= len(dims) <= 3                                  # tactical owns 3 proxies max
    assert all(d.edge in ("home", "away") for d in dims)       # near-even rows suppressed
    groups = [d.group for d in dims]
    assert len(groups) == len(set(groups))                     # one per group
    # tactical no longer duplicates Snapshot/Attacking/Discipline metrics
    names = {d.name for d in dims}
    assert not (names & {"Ball Share", "Shot Volume", "Shot Accuracy", "Card & Foul Rate"})


def test_proxy_edge_direction_and_suppression():
    dims = {d.name: d for d in A.proxy_dimensions(_STRONG, _WEAK, home_name="H", away_name="A")}
    assert dims["Defensive Shot Pressure"].edge == "home"      # H faces fewer shots (lower better)
    # all three proxies equal → nothing meaningful survives
    even_agg = {**_STRONG}
    same = {**_STRONG, "matches": 12}
    assert A.proxy_dimensions(even_agg, same, home_name="H", away_name="A") == []


def test_proxy_confidence_gate_low_sample():
    tiny = {**_STRONG, "matches": 2}
    assert A.proxy_dimensions(tiny, _WEAK, home_name="H", away_name="A") == []


def test_proxy_wording_is_honest():
    dims = A.proxy_dimensions(_STRONG, _WEAK, home_name="H", away_name="A")
    text = " ".join(f"{d.name} {d.evidence}" for d in dims).lower()
    for term in _BANNED:
        assert term not in text, f"banned tactical term leaked: {term}"


def test_shared_traits_detects_league_unusual():
    league = {"shots": 12.5, "shots_faced": 12.5}
    both_high = {"shots": 16, "shots_faced": 12}
    traits = A.shared_traits(both_high, {"shots": 16, "shots_faced": 12}, league)
    assert any("more shots" in t for t in traits)
    assert A.shared_traits({"shots": 12.6, "shots_faced": 12}, {"shots": 12.4, "shots_faced": 12}, league) == []


def test_storylines_trigger_and_dedup():
    stories = A.storylines("H", "A", home_agg=_STRONG, away_agg=_WEAK,
                           home_last5={"matches": 5, "wins": 4, "draws": 1, "losses": 0, "unbeaten": True,
                                       "goals_for": 2.2, "goals_against": 0.6},
                           away_last5={"matches": 5, "wins": 0, "draws": 1, "losses": 4, "unbeaten": False,
                                       "goals_for": 0.6, "goals_against": 2.0, "winless": True},
                           league={"shots": 12.5, "shots_faced": 12.5},
                           home_standing={"conference_rank": 2}, away_standing={"conference_rank": 12},
                           home_home_ppm=2.2, away_away_ppm=0.7)
    assert 1 <= len(stories) <= 5
    themes = [s.theme for s in stories]
    assert len(themes) == len(set(themes))                     # deduped by theme
    ids = {s.rule_id for s in stories}
    assert ids & {"STRONG_HOME", "WEAK_AWAY", "TABLE_GAP", "LOSING_RUN"}


# ============================================================ builder (real) ==
def _synthetic_frame():
    rows = []
    for i in range(10):
        d = f"2026-04-{i+1:02d}"
        rows.append({"event_id": f"G{i}", "team_id": "H", "opponent_id": "A", "is_home": 1,
                     "match_date": d, "goals_for": 2, "goals_against": 0, "total_shots": 16,
                     "shots_on_target": 7, "possession_pct": 57, "total_passes": 500,
                     "accurate_passes": 450, "won_corners": 6, "fouls_committed": 9,
                     "yellow_cards": 1, "red_cards": 0, "total_crosses": 18, "accurate_crosses": 5,
                     "total_tackles": 18, "interceptions": 9, "blocked_shots": 4, "saves": 3,
                     "pk_shots": 0, "shots_faced": 9, "sot_faced": 3, "offsides": 1,
                     "total_clearances": 20})
        rows.append({"event_id": f"G{i}", "team_id": "A", "opponent_id": "H", "is_home": 0,
                     "match_date": d, "goals_for": 0, "goals_against": 2, "total_shots": 9,
                     "shots_on_target": 3, "possession_pct": 43, "total_passes": 400,
                     "accurate_passes": 330, "won_corners": 3, "fouls_committed": 12,
                     "yellow_cards": 2, "red_cards": 0, "total_crosses": 12, "accurate_crosses": 2,
                     "total_tackles": 20, "interceptions": 11, "blocked_shots": 5, "saves": 6,
                     "pk_shots": 0, "shots_faced": 16, "sot_faced": 7, "offsides": 2,
                     "total_clearances": 26})
    return pd.DataFrame(rows)


def _real_game():
    from domain.models import SlateGame
    return SlateGame(league="MLS", game_id="ZZZ", home_id="H", away_id="A",
                     home_name="Homers", away_name="Away FC", home_short="Homers",
                     away_short="Away FC", state="pre",
                     meta={"competition": "MLS Regular Season", "home_record": "9-1-0",
                           "away_record": "2-1-7"})


def test_builder_real_path(monkeypatch):
    from services import mls_game_page as B
    frame = _synthetic_frame()
    monkeypatch.setattr(B.R, "team_match_frame", lambda *a, **k: frame)
    monkeypatch.setattr(B.R, "standings_lookup", lambda tid, *a, **k: (
        {"conference": "Western Conference", "conference_rank": 1, "points": 27} if tid == "H"
        else {"conference": "Western Conference", "conference_rank": 13, "points": 8}))
    page = B.build_mls_game_page(_real_game(), date(2026, 6, 1), date(2026, 6, 1))

    assert page.snapshot.state is B.DataState.AVAILABLE and 6 <= len(page.snapshot.rows) <= 7
    # tactical shows meaningful contrasts (H much stronger) — rows, not a summary
    assert page.tactical.state is B.DataState.AVAILABLE and 1 <= len(page.tactical.rows) <= 3
    assert page.attacking.state is B.DataState.AVAILABLE
    assert page.discipline.state is B.DataState.AVAILABLE
    assert page.storylines.state is B.DataState.AVAILABLE and page.storylines.items
    assert page.players.state is B.DataState.UNAVAILABLE       # unchanged this phase
    assert page.lineups.state is B.DataState.UNAVAILABLE
    assert page.hero.home.standing and "West" in page.hero.home.standing
    # honesty: banned terms absent from tactical rows + summary
    tac_text = (" ".join(f"{r.dimension} {r.explanation}" for r in page.tactical.rows)
                + " " + page.tactical.summary).lower()
    for term in _BANNED:
        assert term not in tac_text
    assert any(r.label == "Ball Share" for r in page.snapshot.rows)
    # honest gaps updated (resolved 'season stats missing')
    labels = [g.label for g in page.honest_gaps.items]
    assert "Team stats, not tracking data" in labels
    assert "Season match stats missing" not in labels


# ============================================ Phase-3B refinement (UX pass) ==
def _sim_frame():
    """Two near-identical clubs across 10 dated matches (draws)."""
    rows = []
    for i in range(10):
        d = f"2026-04-{i+1:02d}"
        for tid, opp, home in (("H", "A", 1), ("A", "H", 0)):
            rows.append({"event_id": f"S{i}", "team_id": tid, "opponent_id": opp, "is_home": home,
                         "match_date": d, "goals_for": 1, "goals_against": 1, "total_shots": 12,
                         "shots_on_target": 4, "possession_pct": 50, "total_passes": 450,
                         "accurate_passes": 385, "won_corners": 4.0, "fouls_committed": 11,
                         "yellow_cards": 1.8, "red_cards": 0, "total_crosses": 14, "accurate_crosses": 3,
                         "total_tackles": 19, "interceptions": 10, "blocked_shots": 4, "saves": 4,
                         "pk_shots": 1, "shots_faced": 12, "sot_faced": 4, "offsides": 1,
                         "total_clearances": 22})
    return pd.DataFrame(rows)


def _build_with(monkeypatch, frame, standings=None):
    from services import mls_game_page as B
    monkeypatch.setattr(B.R, "team_match_frame", lambda *a, **k: frame)
    monkeypatch.setattr(B.R, "standings_lookup", lambda tid, *a, **k: standings)
    return B, B.build_mls_game_page(_real_game(), date(2026, 6, 1), date(2026, 6, 1))


def test_no_metric_duplicated_across_sections(monkeypatch):
    import re
    B, page = _build_with(monkeypatch, _synthetic_frame())
    labels = ([r.label for r in page.snapshot.rows]
              + [r.dimension for r in page.tactical.rows]
              + [d.label for d in page.attacking.dimensions]
              + [r.label for r in page.discipline.rows])
    norm = [re.sub(r"[^a-z ]", "", x.lower()).strip() for x in labels]
    assert len(norm) == len(set(norm)), f"duplicate metric across sections: {norm}"


def test_even_matchup_uses_similar_profile(monkeypatch):
    # near-identical clubs → tactical + attacking + discipline collapse to summaries
    B, page = _build_with(monkeypatch, _sim_frame())
    assert page.tactical.rows == () and page.tactical.summary
    assert "style" in page.tactical.summary.lower()
    assert page.attacking.dimensions == () and page.attacking.summary   # low-signal rows suppressed
    assert page.discipline.rows == () and page.discipline.summary


def _hero_stub():
    from domain.mls_game_page import MLSHero, MLSTeamLine
    def tl(s):
        return MLSTeamLine(name=s, short=s, logo=None, color=None, record=None,
                           form=(), points_display=None)
    return MLSHero(competition="", kickoff="", venue=None, broadcast=None,
                   away=tl("Away"), home=tl("Home"), state="pre", away_score=None,
                   home_score=None, status_detail=None)


def test_penalty_uses_per_match_rate_when_material():
    from services import mls_game_page as B
    ha = {"matches": 13, "pk_attempts": 0.31, "shot_accuracy": 40, "crosses": 15, "cross_accuracy": 25}
    aa = {"matches": 13, "pk_attempts": 0.08, "shot_accuracy": 40, "crosses": 15, "cross_accuracy": 25}
    att = B._build_attacking_real(_hero_stub(), ha, aa)
    pen = [d for d in att.dimensions if "Penalty" in d.label]
    assert pen and "/ match" in pen[0].label                 # per-match rate, not season total
    assert pen[0].home_value == "0.31" and pen[0].away_value == "0.08"


def test_penalty_suppressed_when_rate_low_signal():
    from services import mls_game_page as B
    ha = {"matches": 13, "pk_attempts": 0.15, "shot_accuracy": 40, "crosses": 15, "cross_accuracy": 25}
    aa = {"matches": 13, "pk_attempts": 0.08, "shot_accuracy": 40, "crosses": 15, "cross_accuracy": 25}
    att = B._build_attacking_real(_hero_stub(), ha, aa)   # gap 0.07 < 0.15 threshold
    assert not any("Penalty" in d.label for d in att.dimensions)


def test_red_card_row_notes_sample_size():
    from services import mls_game_page as B
    ha = {"matches": 13, "fouls": 11.0, "yellows": 1.5, "reds_total": 4}
    aa = {"matches": 12, "fouls": 11.0, "yellows": 1.5, "reds_total": 0}
    dis = B._build_discipline_real(_hero_stub(), ha, aa)
    assert any("Red cards" in r.label for r in dis.rows)
    assert "season counts" in dis.note.lower() and "13 matches" in dis.note


def _game_records(hr, ar):
    from domain.models import SlateGame
    return SlateGame(league="MLS", game_id="ZZZ", home_id="H", away_id="A",
                     home_name="Homers", away_name="Away FC", home_short="Homers",
                     away_short="Away FC", state="pre", meta={"home_record": hr, "away_record": ar})


def test_storyline_three_states(monkeypatch):
    from services import mls_game_page as B
    monkeypatch.setattr(B.R, "standings_lookup", lambda *a, **k: None)

    # (3) real data, no rule triggers → AVAILABLE empty with 'no standout'
    monkeypatch.setattr(B.R, "team_match_frame", lambda *a, **k: _synthetic_frame())
    monkeypatch.setattr(B.A, "storylines", lambda *a, **k: [])
    p3 = B.build_mls_game_page(_game_records("5-5-5", "5-5-5"), date(2026, 6, 1), date(2026, 6, 1))
    assert p3.storylines.state is B.DataState.AVAILABLE and not p3.storylines.items
    assert "no standout" in p3.storylines.note.lower()

    # (2) partial data (one team, tiny sample) → PARTIAL
    partial = _synthetic_frame()
    partial = partial[partial["team_id"] == "H"].head(2)
    monkeypatch.setattr(B.R, "team_match_frame", lambda *a, **k: partial)
    p2 = B.build_mls_game_page(_game_records("5-5-5", "5-5-5"), date(2026, 6, 1), date(2026, 6, 1))
    assert p2.storylines.state is B.DataState.PARTIAL

    # (1) no collected data + balanced records → UNAVAILABLE (not 'no standout')
    monkeypatch.setattr(B.R, "team_match_frame", lambda *a, **k: pd.DataFrame())
    p1 = B.build_mls_game_page(_game_records("5-5-5", "5-5-5"), date(2026, 6, 1), date(2026, 6, 1))
    assert p1.storylines.state is B.DataState.UNAVAILABLE


# ============================================ match events (Option C) =========
def _summary_with_events():
    return {"keyEvents": [
        {"id": "1", "type": {"text": "Yellow Card"}, "clock": {"displayValue": "7'"},
         "period": {"number": 1}, "team": {"id": "100"},
         "participants": [{"athlete": {"id": "9", "displayName": "Booker"}}]},
        {"id": "2", "type": {"text": "Goal - Header"}, "clock": {"displayValue": "42'"},
         "period": {"number": 1}, "team": {"id": "100"},
         "text": "Goal! header from a corner.",
         "participants": [{"athlete": {"id": "5", "displayName": "Scorer"}},
                          {"athlete": {"id": "6", "displayName": "Assister"}}]},
        {"id": "3", "type": {"text": "Penalty - Scored"}, "clock": {"displayValue": "45'+7'"},
         "period": {"number": 1}, "team": {"id": "100"},
         "text": "converts the penalty.",
         "participants": [{"athlete": {"id": "7", "displayName": "Taker"}}]},
        {"id": "4", "type": {"text": "Goal"}, "clock": {"displayValue": "88'"},
         "period": {"number": 2}, "team": {"id": "200"},
         "text": "left footed shot to the bottom right corner.",   # NOT a set piece
         "participants": [{"athlete": {"id": "8", "displayName": "Late"}}]},
        {"id": "5", "type": {"text": "Substitution"}, "clock": {"displayValue": "60'"},
         "period": {"number": 2}, "team": {"id": "200"},
         "participants": [{"athlete": {"id": "1", "displayName": "In"}},
                          {"athlete": {"id": "2", "displayName": "Out"}}]},
        {"id": "6", "type": {"text": "Kickoff"}, "clock": {"displayValue": ""}},  # skipped
    ]}


def test_parse_key_events_categories_and_sources():
    ev = E.parse_key_events(_summary_with_events())
    assert len(ev) == 5                                   # kickoff skipped
    by = {e["seq"]: e for e in ev}
    assert by["1"]["category"] == "card"
    assert by["2"]["category"] == "goal" and by["2"]["goal_source"] == "set_piece"  # "from a corner"
    assert by["3"]["category"] == "goal" and by["3"]["goal_source"] == "penalty"
    # "bottom right corner" is shot placement, NOT a set piece
    assert by["4"]["category"] == "goal" and by["4"]["goal_source"] == "open_play"
    assert by["5"]["category"] == "sub"


def test_parse_key_events_minute_buckets():
    by = {e["seq"]: e for e in E.parse_key_events(_summary_with_events())}
    assert by["1"]["bucket"] == "0-15"
    assert by["2"]["minute"] == 42 and by["2"]["bucket"] == "31-45"
    # first-half stoppage folds into 31-45 (not 46-60), stoppage captured
    assert by["3"]["minute"] == 45 and by["3"]["stoppage"] == 7 and by["3"]["bucket"] == "31-45"
    assert by["4"]["bucket"] == "76-90+"


def test_parse_key_events_participants():
    by = {e["seq"]: e for e in E.parse_key_events(_summary_with_events())}
    assert by["2"]["primary_name"] == "Scorer" and by["2"]["secondary_name"] == "Assister"
    assert by["5"]["primary_name"] == "In" and by["5"]["secondary_name"] == "Out"
    assert by["1"]["secondary_name"] is None             # card has no second athlete


def test_store_events_idempotent_and_fully_collected(tmp_path):
    db = tmp_path / "ev.db"
    with sqlite3.connect(db) as conn:
        mls_store.ensure_tables(conn)
        mls_store.upsert_team_stats(conn, [{"event_id": "M1", "team_id": "100"},
                                           {"event_id": "M1", "team_id": "200"}])
        # only team stats so far → not fully collected
        assert mls_store.fully_collected_event_ids(conn) == set()
        rows = [{"match_id": "M1", "seq": "1"}, {"match_id": "M1", "seq": "2"}]
        mls_store.upsert_events(conn, rows)
        mls_store.upsert_events(conn, rows)              # idempotent
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM mls_match_events").fetchone()[0] == 2
        assert mls_store.fully_collected_event_ids(conn) == {"M1"}


def _seed_events_db(tmp_path):
    """Team H scores late + from set pieces; concedes to O. Dated matches."""
    db = tmp_path / "evrepo.db"
    matches, events = [], []
    for i, d in enumerate(["2026-03-01", "2026-03-08", "2026-03-15", "2026-03-22"]):
        eid = f"E{i}"
        matches.append({"event_id": eid, "match_date": d, "home_team_id": "H", "away_team_id": "O",
                        "home_score": 2, "away_score": 1})
        # H: one set-piece goal late (76-90+), one open-play; O: one goal 46-60
        events += [
            {"match_id": eid, "seq": f"{eid}a", "category": "goal", "goal_source": "set_piece",
             "bucket": "76-90+", "team_id": "H"},
            {"match_id": eid, "seq": f"{eid}b", "category": "goal", "goal_source": "open_play",
             "bucket": "16-30", "team_id": "H"},
            {"match_id": eid, "seq": f"{eid}c", "category": "goal", "goal_source": "open_play",
             "bucket": "46-60", "team_id": "O"},
        ]
    with sqlite3.connect(db) as conn:
        mls_store.ensure_tables(conn)
        mls_store.upsert_matches(conn, matches)
        mls_store.upsert_events(conn, events)
        conn.commit()
    return db


def test_repository_event_patterns_leakage_and_shares(tmp_path):
    db = _seed_events_db(tmp_path)
    p = R.team_event_patterns("H", date(2026, 5, 1), db_path=db)
    assert p["matches"] == 4 and p["goals"] == 8 and p["conceded"] == 4
    assert p["set_piece_share"] == pytest.approx(0.5)     # 4 of 8 set-piece
    assert p["late_scored_share"] == pytest.approx(0.5)   # 4 of 8 in 76-90+
    # leakage-safe: strictly before the date, and exclusion works
    early = R.team_event_patterns("H", date(2026, 3, 16), db_path=db)
    assert early["goals"] == 6                            # E0,E1,E2 (E3 on 03-22 excluded)
    excl = R.team_event_patterns("H", date(2026, 5, 1), exclude_event_id="E0", db_path=db)
    assert excl["goals"] == 6                             # selected match removed


def test_event_timeline_cues_and_storylines():
    home = {"goals": 20, "conceded": 14, "early_scored_share": 0.10, "late_scored_share": 0.40,
            "late_conceded_share": 0.20, "set_piece_share": 0.40, "set_piece_goals": 8}
    away = {"goals": 18, "conceded": 20, "early_scored_share": 0.25, "late_scored_share": 0.10,
            "late_conceded_share": 0.40, "set_piece_share": 0.15, "set_piece_goals": 3}
    cues = A.event_timeline_cues("Home", "Away", home, away)
    assert "Late match" in cues and "Home score late" in cues["Late match"]
    assert "0–15'" in cues and "Away start fast" in cues["0–15'"]
    stories = A.event_storylines("Home", "Away", home, away)
    ids = {s.rule_id for s in stories}
    assert "SET_PIECE_THREAT" in ids and "LATE_GOALS" in ids and "LATE_LEAK" in ids
    # min-sample gate: too few goals → nothing
    assert A.event_storylines("Home", "Away", {"goals": 5, "conceded": 5}, {"goals": 5}) == []


def test_builder_wires_event_cues(monkeypatch):
    from services import mls_game_page as B
    frame = _sim_frame()   # even teams → weak team storylines, so event stories rank in
    monkeypatch.setattr(B.R, "team_match_frame", lambda *a, **k: frame)
    monkeypatch.setattr(B.R, "standings_lookup", lambda *a, **k: None)
    monkeypatch.setattr(B.R, "team_event_patterns", lambda tid, *a, **k: (
        {"goals": 20, "conceded": 14, "early_scored_share": 0.10, "late_scored_share": 0.40,
         "late_conceded_share": 0.20, "set_piece_share": 0.40, "set_piece_goals": 8}
        if tid == "H" else
        {"goals": 16, "conceded": 20, "early_scored_share": 0.12, "late_scored_share": 0.15,
         "late_conceded_share": 0.20, "set_piece_share": 0.15, "set_piece_goals": 2}))
    page = B.build_mls_game_page(_real_game(), date(2026, 6, 1), date(2026, 6, 1))
    # a timeline phase now carries a data cue, and a set-piece event storyline surfaces
    assert any(ph.kind == "data" for ph in page.timeline.phases)
    assert any("set pieces" in s.title or "finish strong" in s.title for s in page.storylines.items)
    assert "Match events are used at a basic level" in [g.label for g in page.honest_gaps.items]
