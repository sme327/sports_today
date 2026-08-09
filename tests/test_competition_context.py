"""Competition context on SlateGame — where a game sits in its competition.

Season, phase (preseason/regular/postseason), week, round, competition and neutral
site are first-class typed fields rather than ad-hoc `meta` strings, so every league
answers the question the same way and later work (postseason mode, series/bracket
models, editorial signals) can rely on them.

The honesty rule under test: a source that does not supply a field leaves it None and
the UI omits it. Nothing here is ever guessed.
"""

from __future__ import annotations

from datetime import datetime

from domain.models import SlateGame
from services.schedule_cache import game_from_dict, game_to_dict
from src import espn_scoreboard, mlb_api


# --- normalization: one vocabulary across every source -----------------------

def test_espn_phase_prefers_slug_over_numeric_type():
    # ESPN sends both; the slug is the more reliable of the two.
    assert espn_scoreboard.season_phase("preseason-2", 2) == "preseason"
    assert espn_scoreboard.season_phase("post-season", 2) == "postseason"
    assert espn_scoreboard.season_phase("regular-season", 1) == "regular"


def test_espn_phase_falls_back_to_numeric_type():
    assert espn_scoreboard.season_phase(None, 1) == "preseason"
    assert espn_scoreboard.season_phase(None, 2) == "regular"
    assert espn_scoreboard.season_phase(None, 3) == "postseason"
    assert espn_scoreboard.season_phase(None, 4) == "postseason"


def test_espn_phase_is_none_when_the_source_says_nothing():
    # Unknown is unknown — never defaulted to "regular".
    assert espn_scoreboard.season_phase(None, None) is None
    assert espn_scoreboard.season_phase("", 99) is None


def test_mlb_and_espn_agree_on_the_same_words():
    """A live MLB game and a live NFL game must describe their phase identically —
    and match the vocabulary the ingested NFL feed already stores."""
    assert mlb_api._phase("R") == espn_scoreboard.season_phase("regular-season", 2)
    assert mlb_api._phase("W") == espn_scoreboard.season_phase("post-season", 3)
    assert {mlb_api._phase(c) for c in "FDLWP"} == {"postseason"}
    assert mlb_api._phase("S") == "preseason"


def test_mlb_phase_none_for_allstar_and_unknown_codes():
    for code in ("A", "E", "", None, "zzz"):
        assert mlb_api._phase(code) is None


# --- the human label ---------------------------------------------------------

def test_context_label_prefers_the_leagues_own_round_wording():
    g = SlateGame(league="NFL", game_id="1", round_name="Preseason · Wk 2",
                  phase="preseason", week=2)
    assert g.context_label == "Preseason · Wk 2"


def test_context_label_falls_back_through_week_then_phase():
    assert SlateGame(league="NFL", game_id="1", week=3).context_label == "Week 3"
    assert SlateGame(league="MLB", game_id="1", phase="postseason").context_label == "Postseason"


def test_context_label_is_none_when_nothing_is_known():
    # No invented "Regular Season" for a league that never told us.
    assert SlateGame(league="MLS", game_id="1").context_label is None


def test_context_label_adds_competition_and_neutral_site():
    g = SlateGame(league="WC", game_id="1", round_name="Round of 16",
                  competition="FIFA World Cup", neutral_site=True)
    assert g.context_label == "FIFA World Cup · Round of 16 · Neutral site"


def test_context_label_does_not_repeat_the_competition():
    g = SlateGame(league="MLS", game_id="1", round_name="MLS Cup Playoffs",
                  competition="MLS Cup Playoffs")
    assert g.context_label == "MLS Cup Playoffs"


def test_context_label_collapses_an_overlapping_competition():
    """Real MLS shape: competition "MLS Regular Season" with phase "regular", which
    renders "Regular Season". Joining them gave "MLS Regular Season · Regular Season";
    the fuller competition name wins instead."""
    g = SlateGame(league="MLS", game_id="1", phase="regular",
                  competition="MLS Regular Season")
    assert g.context_label == "MLS Regular Season"


# --- what actually reaches the card ------------------------------------------

def test_ordinary_regular_season_shows_no_context():
    """The common case. Most games are ordinary; "Regular Season" on every card is
    noise, so the card omits it entirely."""
    g = SlateGame(league="MLB", game_id="1", phase="regular", round_name="Regular Season")
    assert g.context_label == "Regular Season"     # the full label still exists
    assert g.notable_context is None               # …but nothing is shown


def test_postseason_and_preseason_are_always_notable():
    assert SlateGame(league="MLB", game_id="1", phase="postseason",
                     round_name="World Series").notable_context == "World Series"
    assert SlateGame(league="NFL", game_id="1", phase="preseason", week=2,
                     round_name="Preseason · Wk 2").notable_context == "Preseason · Wk 2"


def test_regular_season_week_is_shortened_to_just_the_week():
    """Football's week matters; "Regular Season · Wk 1" spends words on what the
    reader already assumes."""
    g = SlateGame(league="NFL", game_id="1", phase="regular", week=1,
                  round_name="Regular Season · Wk 1")
    assert g.notable_context == "Week 1"


def test_neutral_site_is_notable_and_still_shortens_the_week():
    """Real NCAAF week-1 shape. The week shortening applies here too — a neutral
    site is worth saying, "Regular Season" still isn't."""
    g = SlateGame(league="NCAAF", game_id="1", phase="regular", week=1,
                  round_name="Regular Season · Wk 1", neutral_site=True)
    assert g.notable_context == "Week 1 · Neutral site"


def test_tournament_round_is_notable_even_without_a_phase():
    g = SlateGame(league="World Cup", game_id="1", round_name="Round of 16",
                  competition="FIFA World Cup")
    assert g.notable_context == "FIFA World Cup · Round of 16"


def test_unknown_context_shows_nothing():
    assert SlateGame(league="MLS", game_id="1").notable_context is None


def test_card_renders_context_only_when_notable():
    from components.game_cards import game_card_html
    playoff = SlateGame(league="MLB", game_id="1", away_name="A", home_name="B",
                        phase="postseason", round_name="World Series")
    ordinary = SlateGame(league="MLB", game_id="2", away_name="A", home_name="B",
                         phase="regular", round_name="Regular Season")
    assert "World Series" in game_card_html(playoff, "today")
    assert "game-context" not in game_card_html(ordinary, "today")


def test_is_postseason_flag():
    assert SlateGame(league="MLB", game_id="1", phase="postseason").is_postseason
    assert not SlateGame(league="MLB", game_id="1", phase="regular").is_postseason
    assert not SlateGame(league="MLB", game_id="1").is_postseason


# --- cache compatibility -----------------------------------------------------

def test_context_survives_a_cache_round_trip():
    g = SlateGame(league="NFL", game_id="7", start_time=datetime(2026, 9, 13, 17, 0),
                  season=2026, phase="regular", week=2, round_name="Week 2",
                  competition=None, neutral_site=True)
    back = game_from_dict(game_to_dict(g))
    assert (back.season, back.phase, back.week) == (2026, "regular", 2)
    assert back.round_name == "Week 2" and back.neutral_site is True


def test_rows_cached_before_these_fields_existed_still_load():
    """Old cache entries have no competition keys at all; they must deserialize to
    'unknown' rather than raising — the cache is not versioned."""
    legacy = {"league": "MLB", "game_id": "42", "start_time": None,
              "away_name": "A", "home_name": "B"}
    g = game_from_dict(legacy)
    assert g.season is None and g.phase is None and g.week is None
    assert g.neutral_site is False
    assert g.context_label is None
