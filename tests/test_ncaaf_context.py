"""College football's Week 1 problem: a schedule, two 0-0 teams, and nothing to say.

`services/editorial` requires four games of record before it speaks, so on the opening
weekend it produces literally zero signals and the matchup page renders a shrug — the
state these tests exist to keep fixed. They cover what the page can honestly say
*before* a record exists, and just as importantly what it must refuse to say.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest

from domain.models import SlateGame
from services import ncaaf_context
from src import ncaaf_store

PRIOR = 2025


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "ncaaf.db"
    with sqlite3.connect(path) as conn:
        ncaaf_store.ensure_tables(conn)
    return path


def add_team(db, team_id, name, division="FBS", overall="9-4", wins=9, losses=4,
             conference="Big Ten"):
    with sqlite3.connect(db) as conn:
        ncaaf_store.upsert_team_seasons(conn, [(
            PRIOR, team_id, name, division, conference, overall, wins, losses, "now")])


def add_passer(db, team_id, athlete_id="1", name="A Passer", yards=3000.0,
               status="returning", current_team_id=None):
    with sqlite3.connect(db) as conn:
        ncaaf_store.upsert_passers(conn, [(
            PRIOR, team_id, athlete_id, name, "QB", yards, status, current_team_id,
            "now")])


def game(**over) -> SlateGame:
    meta = {"away_team_id": "10", "home_team_id": "20"}
    meta.update(over.pop("meta", {}))
    base = dict(league="NCAAF", game_id="1", start_time=datetime(2026, 8, 29, 19, 0),
                away_name="Away State", home_name="Home State",
                away_short="Away State", home_short="Home State",
                away_record="0-0", home_record="0-0", meta=meta)
    base.update(over)
    return SlateGame(**base)


# --- the empty state this feature exists to replace --------------------------------

def test_zero_zero_teams_still_produce_no_editorial_signals():
    """The premise. If this ever starts passing signals, the context service is no
    longer the only thing standing between the reader and a blank page."""
    from services import editorial
    detail = editorial.interest(game(home_rank=14), None)
    assert detail.signals == ()


def test_nothing_stored_means_nothing_claimed(db):
    """An unknown team gets silence, not an invented record."""
    assert ncaaf_context.signals_for(game(), prior_season=PRIOR, db_path=db) == ()


# --- last season, with its vintage -------------------------------------------------

def test_last_season_names_the_year_and_both_records(db):
    add_team(db, "10", "Away State", overall="3-9", wins=3, losses=9)
    add_team(db, "20", "Home State", overall="9-4")
    sig = ncaaf_context.last_season_signal(
        game(), ncaaf_context.load_team_seasons(["10", "20"], PRIOR, db), PRIOR)
    assert "3-9 in 2025" in sig.detail and "9-4 in 2025" in sig.detail
    assert "2025 record" == sig.label


def test_a_prior_record_always_carries_the_turnover_caveat(db):
    """The record alone would read as form. It is background, and the page says so in
    the same breath rather than leaving the reader to remember it."""
    add_team(db, "10", "Away State")
    add_team(db, "20", "Home State")
    sig = ncaaf_context.last_season_signal(
        game(), ncaaf_context.load_team_seasons(["10", "20"], PRIOR, db), PRIOR)
    assert any("turn over" in c for c in sig.caveats)


def test_a_team_with_no_stored_season_is_named_as_missing(db):
    """Half a fact is fine; pretending it is whole is not."""
    add_team(db, "20", "Home State")
    sig = ncaaf_context.last_season_signal(
        game(), ncaaf_context.load_team_seasons(["10", "20"], PRIOR, db), PRIOR)
    assert "Home State were 9-4" in sig.detail
    assert any("No 2025 record held" in c for c in sig.caveats)


# --- the division mismatch ---------------------------------------------------------

def test_fbs_against_fcs_is_called_a_mismatch(db):
    add_team(db, "10", "Away State", division="FCS", overall="6-5")
    add_team(db, "20", "Home State", division="FBS")
    sig = ncaaf_context.division_signal(
        game(), ncaaf_context.load_team_seasons(["10", "20"], PRIOR, db))
    assert "FCS" in sig.detail
    assert any("one-sided" in c for c in sig.caveats)


def test_two_teams_in_the_same_division_get_no_mismatch_notice(db):
    add_team(db, "10", "Away State", division="FBS")
    add_team(db, "20", "Home State", division="FBS")
    assert ncaaf_context.division_signal(
        game(), ncaaf_context.load_team_seasons(["10", "20"], PRIOR, db)) is None


# --- the quarterback ---------------------------------------------------------------

def test_a_returning_passer_is_reported_as_continuity(db):
    add_passer(db, "20", status="returning", name="Real Passer", yards=3431)
    sig = ncaaf_context.quarterback_signal(
        game(), ncaaf_context.load_passers(["10", "20"], PRIOR, db), {}, PRIOR)
    assert "return Real Passer" in sig.detail and "3,431 yds" in sig.detail
    assert sig.label == "QB returns"


def test_a_transfer_names_the_destination_when_it_is_known(db):
    add_team(db, "99", "Elsewhere U")
    add_passer(db, "20", status="transferred", name="Gone Guy", current_team_id="99")
    passers = ncaaf_context.load_passers(["10", "20"], PRIOR, db)
    dests = {"99": "Elsewhere U"}
    sig = ncaaf_context.quarterback_signal(game(), passers, dests, PRIOR)
    assert "transferred to Elsewhere U" in sig.detail
    assert sig.label == "QB turnover"


def test_a_transfer_to_an_unknown_team_says_elsewhere_not_a_guess(db):
    add_passer(db, "20", status="transferred", name="Gone Guy", current_team_id="404")
    sig = ncaaf_context.quarterback_signal(
        game(), ncaaf_context.load_passers(["10", "20"], PRIOR, db), {}, PRIOR)
    assert "transferred elsewhere" in sig.detail


def test_an_unchecked_passer_is_never_reported_as_departed(db):
    """status NULL means the follow-up lookup failed. Reporting that as "he is gone"
    would be the worst error this feature can make, and it is one bad `or` away."""
    add_passer(db, "20", status=None)
    assert ncaaf_context.quarterback_signal(
        game(), ncaaf_context.load_passers(["10", "20"], PRIOR, db), {}, PRIOR) is None


def test_the_passer_caveat_refuses_to_call_yards_quality(db):
    add_passer(db, "20", status="returning")
    sig = ncaaf_context.quarterback_signal(
        game(), ncaaf_context.load_passers(["10", "20"], PRIOR, db), {}, PRIOR)
    assert any("do not measure him" in c for c in sig.caveats)


# --- rank and occasion -------------------------------------------------------------

def test_a_ranked_team_outside_the_top_ten_gets_a_mention():
    """editorial speaks for a lone ranked team only inside the top ten; #14 on opening
    weekend is the most notable thing on the card and went unmentioned."""
    sig = ncaaf_context.rank_signal(game(home_rank=14))
    assert sig is not None and "#14" in sig.detail


def test_a_top_ten_team_is_left_to_the_editorial_read():
    """No duplicate: editorial already covers this case."""
    assert ncaaf_context.rank_signal(game(home_rank=3)) is None


def test_the_unranked_sentinel_is_not_treated_as_a_rank():
    """ESPN sends 99 for unranked. Printing "#99" would be worse than silence."""
    assert ncaaf_context.rank_signal(game(home_rank=99)) is None


def test_a_named_game_abroad_is_surfaced():
    sig = ncaaf_context.occasion_signal(game(neutral_site=True, meta={
        "event_note": "Aer Lingus College Football Classic",
        "venue_city": "Dublin", "venue_country": "Ireland"}))
    assert "Aer Lingus" in sig.detail and "Dublin" in sig.detail


def test_an_ordinary_home_game_has_no_occasion():
    assert ncaaf_context.occasion_signal(game(meta={
        "venue_city": "Ypsilanti", "venue_state": "MI", "venue_country": "USA"})) is None


# --- assembly ----------------------------------------------------------------------

def test_signals_come_back_in_reading_order(db):
    add_team(db, "10", "Away State", division="FCS", overall="6-5")
    add_team(db, "20", "Home State", division="FBS")
    add_passer(db, "20", status="returning")
    kinds = [s.kind for s in ncaaf_context.signals_for(
        game(home_rank=14), prior_season=PRIOR, db_path=db)]
    assert kinds == ["last_season", "qb_turnover", "division_gap",
                     "ranked_outside_top10"]


def test_a_missing_database_is_survived_not_raised(tmp_path):
    """The context is enrichment. A page that cannot reach it shows less, never 500s."""
    assert ncaaf_context.signals_for(
        game(), prior_season=PRIOR, db_path=tmp_path / "nope.db") == ()


# --- the page itself ---------------------------------------------------------------

def test_the_matchup_page_renders_the_context_instead_of_the_shrug(db, monkeypatch):
    """The whole point, end to end: with 0-0 records the page used to render only
    "not enough of this league has played yet". It must now carry the read."""
    from services import ncaaf_context as ctx
    from web import simple_game

    add_team(db, "10", "Away State", division="FCS", overall="2-10")
    add_team(db, "20", "Home State", division="FBS", overall="12-2")
    add_passer(db, "20", status="returning", name="Real Passer", yards=3100)

    real = ctx.signals_for
    monkeypatch.setattr(ctx, "signals_for", lambda g, *, prior_season: real(
        g, prior_season=prior_season, db_path=db))

    html = simple_game.simple_game_context(game(), date(2026, 8, 29),
                                           "today")["editorial_html"]
    assert "12-2 in 2025" in html
    assert "Real Passer" in html
    assert "FCS" in html
    assert "Not enough of this league has played yet" not in html


def test_the_shrug_survives_for_a_league_with_no_context(db):
    """NHL and the rest keep the honest empty state — this is an NCAAF feature, not a
    silent change to every schedule-only league."""
    from web import simple_game
    nhl = SlateGame(league="NHL", game_id="9", start_time=datetime(2026, 10, 8, 19, 0),
                    away_name="Away", home_name="Home", away_short="Away",
                    home_short="Home", away_record="0-0", home_record="0-0", meta={})
    context = simple_game.simple_game_context(nhl, date(2026, 10, 8), "today")
    assert "Not enough of this league has played yet" in context["editorial_html"]
