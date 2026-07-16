"""Offline tests for Final-score V1: parsers, model/cache, and card rendering."""

from __future__ import annotations

from datetime import datetime

from components.game_cards import game_card_html
from domain.models import SlateGame
from services.schedule_cache import game_from_dict, game_to_dict
from src.mlb_api import _parse_schedule
from src.wnba_api import _parse_events
from src.world_cup_api import _parse_espn


# --------------------------------------------------------------- MLB parser --
def _mlb_game(pk, abstract, detailed, away_sc=None, home_sc=None, away_win=None, home_win=None):
    away = {"team": {"id": 121, "name": "New York Mets", "teamName": "Mets", "abbreviation": "NYM"}}
    home = {"team": {"id": 143, "name": "Philadelphia Phillies", "teamName": "Phillies", "abbreviation": "PHI"}}
    if away_sc is not None:
        away["score"] = away_sc
    if home_sc is not None:
        home["score"] = home_sc
    if away_win is not None:
        away["isWinner"] = away_win
    if home_win is not None:
        home["isWinner"] = home_win
    return {"gamePk": pk, "gameDate": "2026-07-16T23:05:00Z",
            "status": {"detailedState": detailed, "abstractGameState": abstract},
            "teams": {"away": away, "home": home}, "venue": {"name": "CBP"}}


def test_mlb_pregame_has_no_score():
    g = _parse_schedule({"dates": [{"games": [_mlb_game(1, "Preview", "Scheduled")]}]})[0]
    assert g["state"] == "pre"
    assert g["away_score"] is None and g["home_score"] is None
    assert g["winner"] is None


def test_mlb_live_score():
    g = _parse_schedule({"dates": [{"games": [_mlb_game(2, "Live", "In Progress", 2, 3)]}]})[0]
    assert g["state"] == "live"
    assert g["away_score"] == 2 and g["home_score"] == 3
    assert g["winner"] is None  # no winner mid-game


def test_mlb_final_score_and_winner():
    g = _parse_schedule({"dates": [{"games": [
        _mlb_game(3, "Final", "Final", 5, 14, away_win=False, home_win=True)]}]})[0]
    assert g["state"] == "final"
    assert (g["away_score"], g["home_score"]) == (5, 14)
    assert g["winner"] == "home"
    assert g["status_detail"] == "Final"


# ------------------------------------------------------------- ESPN parsers --
def _espn(state, detail, home_sc=None, away_sc=None, home_win=None, away_win=None):
    home = {"homeAway": "home", "team": {"displayName": "Seattle Storm"}}
    away = {"homeAway": "away", "team": {"displayName": "Las Vegas Aces"}}
    if home_sc is not None:
        home["score"] = home_sc
    if away_sc is not None:
        away["score"] = away_sc
    if home_win is not None:
        home["winner"] = home_win
    if away_win is not None:
        away["winner"] = away_win
    return {"events": [{"id": "1", "date": "2026-07-15T23:00Z",
                        "status": {"type": {"state": state, "detail": detail, "shortDetail": detail}},
                        "competitions": [{"competitors": [home, away], "venue": {"fullName": "Arena"}}]}]}


def test_wnba_pregame_and_final():
    pre = _parse_events(_espn("pre", "7:00 PM ET"))[0]
    assert pre["state"] == "pre" and pre["away_score"] is None and pre["winner"] is None
    fin = _parse_events(_espn("post", "Final", home_sc="90", away_sc="87", home_win=True, away_win=False))[0]
    assert fin["state"] == "final"
    assert (fin["away_score"], fin["home_score"]) == (87, 90)  # strings coerced to int
    assert fin["winner"] == "home"


def test_wnba_live_score():
    live = _parse_events(_espn("in", "3rd Quarter", home_sc="55", away_sc="50"))[0]
    assert live["state"] == "live"
    assert (live["away_score"], live["home_score"]) == (50, 55)
    assert live["status_detail"] == "3rd Quarter"


def test_world_cup_final_winner():
    g = _parse_espn(_espn("post", "AET", home_sc="1", away_sc="2", home_win=False, away_win=True))[0]
    assert g["state"] == "final"
    assert (g["away_score"], g["home_score"]) == (2, 1)
    assert g["winner"] == "away"
    assert g["status_detail"] == "AET"


def test_missing_score_fields_are_none():
    # A completed-looking status but no score keys at all.
    g = _parse_events(_espn("post", "Final"))[0]
    assert g["away_score"] is None and g["home_score"] is None
    assert g["state"] == "final"


# ----------------------------------------------- model + cache round-trip ----
def test_old_cached_row_without_new_fields_deserializes():
    # A SlateGame dict serialized before Final-score V1 (no score/state keys).
    old = {"league": "MLB", "game_id": "1", "start_time": "2026-07-16T23:00:00+00:00",
           "away_name": "New York Mets", "home_name": "Philadelphia Phillies",
           "away_short": "Mets", "home_short": "Phillies", "meta": {}}
    g = game_from_dict(old)
    assert isinstance(g, SlateGame)
    assert g.away_score is None and g.state is None and g.winner is None
    assert not g.has_score and not g.is_final and not g.is_live


def test_cache_round_trip_preserves_scores():
    g = SlateGame(league="MLB", game_id="9", start_time=datetime(2026, 7, 16, 23, 0),
                  away_score=5, home_score=14, state="final", winner="home", status_detail="Final")
    back = game_from_dict(game_to_dict(g))
    assert back.away_score == 5 and back.home_score == 14
    assert back.state == "final" and back.winner == "home" and back.is_final


# ------------------------------------------------------------- rendering -----
def _sg(**kw):
    base = dict(league="MLB", game_id="1", start_time=datetime(2026, 7, 16, 23, 5),
                away_name="New York Mets", home_name="Philadelphia Phillies",
                away_short="Mets", home_short="Phillies",
                meta={"away_pitcher": "A", "home_pitcher": "B"})
    base.update(kw)
    return SlateGame(**base)


def test_card_pregame_shows_time_not_score():
    html = game_card_html(_sg(state="pre"), "tomorrow")
    assert "game-time" in html and "at-sign" in html
    assert "game-score" not in html and "game-state" not in html


def test_card_live_shows_score_and_live_badge():
    html = game_card_html(_sg(state="live", away_score=2, home_score=3,
                              status_detail="3rd Inning"), "today")
    assert 'game-state live' in html and "LIVE" in html
    assert 'game-card--live' in html     # state class drives the accent bar
    assert 'game-score' in html and ">2<" in html and ">3<" in html


def test_card_final_shows_score_and_winner_emphasis():
    html = game_card_html(_sg(state="final", away_score=5, home_score=14, winner="home"), "today")
    assert 'game-state final' in html and "Final" in html
    assert 'game-card--final' in html
    assert 'game-score' in html
    assert 'class="gs win"' in html      # winner (home) score emphasized
    assert 'class="team home loss"' not in html  # home is winner, not loss
    assert 'class="team loss"' in html   # away side dimmed


def test_card_pregame_has_no_state_class():
    html = game_card_html(_sg(state="pre"), "tomorrow")
    assert "game-card--live" not in html and "game-card--final" not in html


# ---------------------------------------------- state grouping / ordering ----
def test_group_games_by_state_orders_live_upcoming_final():
    from components.game_cards import group_games_by_state
    g_pre = _sg(game_id="p", state="pre", start_time=datetime(2026, 7, 16, 20, 0))
    g_live = _sg(game_id="l", state="live", start_time=datetime(2026, 7, 16, 18, 0))
    g_final = _sg(game_id="f", state="final", start_time=datetime(2026, 7, 16, 13, 0))
    live, upcoming, final = group_games_by_state([g_pre, g_final, g_live])
    assert [g.game_id for g in live] == ["l"]
    assert [g.game_id for g in upcoming] == ["p"]
    assert [g.game_id for g in final] == ["f"]


def test_group_chronological_within_group_and_none_state_is_upcoming():
    from components.game_cards import group_games_by_state
    early = _sg(game_id="e", state="pre", start_time=datetime(2026, 7, 16, 16, 0))
    late = _sg(game_id="t", state="pre", start_time=datetime(2026, 7, 16, 22, 0))
    unknown = _sg(game_id="u", state=None, start_time=datetime(2026, 7, 16, 12, 0))
    live, upcoming, final = group_games_by_state([late, early, unknown])
    assert live == [] and final == []
    assert [g.game_id for g in upcoming] == ["u", "e", "t"]  # None state -> upcoming
