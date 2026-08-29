"""Ranking a slate whose teams have not played yet.

For the first two weeks of a pro season every team is 0-0, `Standing.win_pct` is None
below `MIN_GAMES`, and every game scored 0 — so the slate could not be ordered at all.
Measured on an opening-night NBA slate before this existed, Celtics-Lakers,
Hornets-Jazz and Wizards-Thunder all scored 0; in January the same three separate to
56, 41 and 35.

The fallback is licensed by roster persistence, and these tests pin both halves of that:
last season may steer the ranking while the record is young, and must stop the moment
the real record can speak.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest

from domain.models import SlateGame
from services import prior_season
from services.editorial import MIN_GAMES, PriorSeason, _blend, interest, parse_record
from src import prior_season_store


def game(away="0-0", home="0-0", league="NBA", **over) -> SlateGame:
    meta = {"away_team_id": "1", "home_team_id": "2"}
    meta.update(over.pop("meta", {}))
    return SlateGame(league=league, game_id="1",
                     start_time=datetime(2026, 10, 21, 19, 0),
                     away_name="Away", home_name="Home",
                     away_short="Away", home_short="Home",
                     away_record=away, home_record=home, meta=meta, **over)


STRONG = PriorSeason(season=2026, wins=64, losses=18, point_differential=11.1)
WEAK = PriorSeason(season=2026, wins=17, losses=65, point_differential=-12.0)


# --- the decay ---------------------------------------------------------------------

def test_last_season_carries_the_whole_weight_before_a_game_is_played():
    pct, weight = _blend(parse_record("0-0"), STRONG)
    assert weight == 1.0
    assert pct == pytest.approx(64 / 82)


def test_the_weight_halves_by_the_midpoint():
    _, weight = _blend(parse_record("1-1"), STRONG)
    assert weight == pytest.approx(0.5)


def test_last_season_is_gone_once_the_real_record_can_speak():
    """At MIN_GAMES the fallback must contribute exactly nothing — past this point the
    scorer has to behave as though it never existed."""
    current = parse_record("3-1")
    assert current.games == MIN_GAMES
    pct, weight = _blend(current, STRONG)
    assert weight == 0.0
    assert pct == current.win_pct


def test_a_partial_record_is_mixed_with_last_season_not_replaced_by_it():
    """Two games in, the real record is half the story and must actually move it."""
    pct, weight = _blend(parse_record("2-0"), WEAK)
    assert weight == pytest.approx(0.5)
    assert pct == pytest.approx(0.5 * (17 / 82) + 0.5 * 1.0)


def test_no_prior_season_leaves_the_original_behaviour_untouched():
    assert _blend(parse_record("0-0"), None) == (None, 0.0)
    assert _blend(parse_record("9-1"), None) == (parse_record("9-1").win_pct, 0.0)


def test_a_prior_season_with_no_games_is_ignored():
    """An empty row must not be read as a .000 team."""
    assert _blend(parse_record("0-0"), PriorSeason(season=2026)) == (None, 0.0)


# --- what the scorer does with it --------------------------------------------------

def test_an_opening_night_slate_can_finally_be_ordered():
    """The whole point. Two good teams must outrank a mismatch and a bad pair, on a
    night when every record is 0-0."""
    good = interest(game(), priors=(
        PriorSeason(season=2026, wins=56, losses=26),
        PriorSeason(season=2026, wins=53, losses=29))).score
    mismatch = interest(game(), priors=(WEAK, STRONG)).score
    bad = interest(game(), priors=(
        PriorSeason(season=2026, wins=22, losses=60),
        PriorSeason(season=2026, wins=24, losses=58))).score
    assert good > mismatch and good > bad
    assert bad > 0                      # ranked, not merely non-zero


def test_without_priors_an_opening_night_game_still_scores_zero():
    """The pre-existing behaviour, unchanged for any league we hold nothing for."""
    assert interest(game(), priors=(None, None)).score == 0


def test_the_reader_is_told_the_ranking_leans_on_last_season():
    detail = interest(game(), priors=(STRONG, WEAK))
    assert any("2026" in c and "last year's teams" in c for c in detail.caveats)


def test_that_caveat_disappears_once_the_records_are_real():
    detail = interest(game("9-1", "3-7"), priors=(STRONG, WEAK))
    assert not any("last year's teams" in c for c in detail.caveats)


def test_last_season_is_shown_as_evidence_with_its_year():
    sig = next(s for s in interest(game(), priors=(STRONG, WEAK)).signals
               if s.kind == "prior_form")
    assert "64-18" in sig.detail and "2026" in sig.detail
    assert "+11.1" in sig.detail          # differential, where the league publishes it


def test_the_prior_form_signal_never_reaches_a_card():
    """It would appear on every card for a fortnight, and a label on everything is a
    label the reader learns to skip."""
    from services.editorial import _CARD_WORTHY
    assert "prior_form" not in _CARD_WORTHY


# --- the store and the lookup ------------------------------------------------------

@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "prior.db"
    with sqlite3.connect(path) as conn:
        prior_season_store.ensure_tables(conn)
        prior_season_store.upsert_standings(conn, [
            ("NBA", 2026, "1", "Away", 17, 65, 0, -12.0, "now"),
            ("NBA", 2026, "2", "Home", 64, 18, 0, 11.1, "now"),
        ])
    prior_season.clear_cache()
    return path


def test_a_game_is_matched_to_both_sides_by_team_id(db):
    away, home = prior_season.pair_for(game(), db_path=db)
    assert away.wins == 17 and home.wins == 64


def test_a_league_we_hold_nothing_for_is_left_alone(db):
    assert prior_season.pair_for(game(league="NCAAF"), db_path=db) == (None, None)


def test_college_football_is_deliberately_excluded():
    """41% of college teams keep their key player against 90-100% in the pro leagues.
    Last season describes a different team there, so it must never steer the ranking."""
    from src.prior_season_collector import LEAGUES
    assert "NCAAF" not in LEAGUES


def test_a_missing_database_is_survived(tmp_path):
    prior_season.clear_cache()
    assert prior_season.pair_for(game(), db_path=tmp_path / "nope.db") == (None, None)


def test_winter_seasons_roll_forward_at_september():
    """ESPN names a winter season for the year it ends, so an October game belongs to
    the next one and looks back at the season just finished."""
    assert prior_season.espn_season(date(2026, 10, 21)) == 2027
    assert prior_season.prior_season_year(date(2026, 10, 21)) == 2026
    assert prior_season.prior_season_year(date(2027, 3, 1)) == 2026
