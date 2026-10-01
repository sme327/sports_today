"""The MLB postseason bracket: written as the ways it could misstate a series.

Fixtures mirror the shape StatsAPI served for the 2026 postseason (verified live on
2026-09-30), including its placeholder teams and its "divisionChamp" quirk. No network.
"""

from __future__ import annotations

from datetime import date

import pytest

from services import mlb_bracket as B
from src import mlb_api

AL = {"NYY": "147", "BOS": "111", "HOU": "117", "CWS": "145", "TB": "139", "CLE": "114"}
NAMES = {"147": "Yankees", "111": "Red Sox", "117": "Astros", "145": "White Sox",
         "139": "Rays", "114": "Guardians"}
SEEDS = {"139": 1, "114": 2, "117": 3, "147": 4, "111": 5, "145": 6}


def _team(abbr: str) -> dict:
    tid = AL[abbr]
    return {"id": tid, "name": f"Full {NAMES[tid]}", "short": NAMES[tid], "abbr": abbr,
            "placeholder": False}


def _slot(label: str, tid: str) -> dict:
    return {"id": tid, "name": label, "short": label, "abbr": label, "placeholder": True}


def _game(pk, n, total, away, home, *, desc, state="pre", winner=None,
          start="2026-09-29T21:00:00Z", if_necessary=False):
    return {
        "game_pk": pk, "series_game": n, "series_total": total, "game_date": start,
        "official_date": start[:10], "game_description": f"{desc} Game {n}",
        "state": state, "winner": winner, "status_detail": None,
        "away_id": away["id"], "home_id": home["id"],
        "away": away["name"], "home": home["name"],
        "away_short": away["short"], "home_short": home["short"],
        "away_abbr": away["abbr"], "home_abbr": home["abbr"],
        "away_logo": None, "home_logo": None,
        "away_placeholder": away["placeholder"], "home_placeholder": home["placeholder"],
        "away_score": None, "home_score": None, "if_necessary": if_necessary,
        "start_time_tbd": False, "venue": "Park",
        "away_pitcher": None, "home_pitcher": None,
    }


def _payload(wc_b_games=None, seeds=SEEDS) -> dict:
    nyy, bos, hou, cws = _team("NYY"), _team("BOS"), _team("HOU"), _team("CWS")
    tb, cle = _team("TB"), _team("CLE")
    wc_b = wc_b_games or [
        _game(1, 1, 3, bos, nyy, desc="AL Wild Card 'B'", state="final", winner="home"),
        _game(2, 2, 3, bos, nyy, desc="AL Wild Card 'B'"),
        _game(3, 3, 3, bos, nyy, desc="AL Wild Card 'B'", if_necessary=True),
    ]
    wc_a = [
        _game(4, 1, 3, cws, hou, desc="AL Wild Card 'A'", state="final", winner="away"),
        _game(5, 2, 3, cws, hou, desc="AL Wild Card 'A'", state="live"),
        _game(6, 3, 3, cws, hou, desc="AL Wild Card 'A'", if_necessary=True),
    ]
    ds_a = [_game(10 + i, i, 5, _slot("NYY/BOS", "9001"), tb, desc="ALDS 'A'",
                  start="2026-10-03T22:30:00Z") for i in (1, 2)]
    ds_b = [_game(20 + i, i, 5, _slot("HOU/CWS", "9002"), cle, desc="ALDS 'B'",
                  start="2026-10-03T17:00:00Z") for i in (1, 2)]
    cs = [_game(30, 1, 7, _slot("AL Lower Seed", "9003"), _slot("AL Higher Seed", "9004"),
                desc="ALCS", start="2026-10-12T07:33:00Z")]
    return {"season": 2026, "seeds": seeds, "head_to_head": {"111-147": {"111": 6, "147": 7}},
            "series": [
                {"series_id": "F_2", "game_type": "F", "games": wc_b},
                {"series_id": "F_1", "game_type": "F", "games": wc_a},
                {"series_id": "D_1", "game_type": "D", "games": ds_a},
                {"series_id": "D_2", "game_type": "D", "games": ds_b},
                {"series_id": "L_1", "game_type": "L", "games": cs},
            ]}


# --- seeds ---------------------------------------------------------------------------

def _standing(tid, mark, league_rank, wc_rank=None, champ=False):
    return {"team": {"id": int(tid)}, "clinchIndicator": mark, "clinched": bool(mark),
            "divisionChamp": champ, "leagueRank": str(league_rank),
            "wildCardRank": str(wc_rank) if wc_rank else None}


def test_seeds_follow_the_clinch_mark_not_the_division_champ_flag():
    # 2026: the source set divisionChamp on the Phillies, a Wild Card. Trusting that flag
    # gave the NL four champions and no seeds at all.
    payload = {"records": [{"league": {"id": 104}, "teamRecords": [
        _standing(158, "z", 1, champ=True), _standing(119, "y", 2, champ=True),
        _standing(144, "y", 3, champ=True), _standing(135, "w", 4, 1),
        _standing(112, "w", 5, 2), _standing(143, "w", 6, 3, champ=True),
        _standing(121, None, 7, 4),
    ]}]}
    assert mlb_api.seeds_from_standings(payload) == {
        "158": 1, "119": 2, "144": 3, "135": 4, "112": 5, "143": 6}


def test_no_seeds_while_a_club_is_in_but_not_yet_which_way():
    payload = {"records": [{"league": {"id": 103}, "teamRecords": [
        _standing(139, "z", 1), _standing(114, "y", 2), _standing(117, "x", 3),
        _standing(147, "w", 4, 1), _standing(111, "w", 5, 2), _standing(145, "w", 6, 3),
    ]}]}
    assert mlb_api.seeds_from_standings(payload) == {}


def test_seeds_that_contradict_the_pairings_are_dropped_not_shown():
    wrong = {**SEEDS, "147": 5, "111": 4}      # the Wild Card host would be the worse seed
    bracket = B.build(_payload(seeds=wrong))
    assert bracket.seeds_dropped == {"AL"}
    assert all(s.high.seed is None and s.low.seed is None for s in bracket.series)


# --- counting a series ---------------------------------------------------------------

def test_series_wins_are_counted_from_final_games_by_team_id():
    s = B.build(_payload()).by_slug("al-wild-card-b")
    assert (s.high.short, s.high.wins, s.low.wins) == ("Yankees", 1, 0)
    assert s.summary == "Yankees lead 1-0"
    assert (s.high.seed, s.low.seed) == (4, 5)


def test_a_decided_series_stops_listing_games_that_will_not_be_played():
    nyy, bos = _team("NYY"), _team("BOS")
    games = [
        _game(1, 1, 3, bos, nyy, desc="AL Wild Card 'B'", state="final", winner="home"),
        _game(2, 2, 3, bos, nyy, desc="AL Wild Card 'B'", state="final", winner="home"),
        _game(3, 3, 3, bos, nyy, desc="AL Wild Card 'B'", if_necessary=True),
    ]
    s = B.build(_payload(wc_b_games=games)).by_slug("al-wild-card-b")
    assert s.winner is s.high and s.summary == "Yankees win 2-0"
    assert s.remaining_games == [] and s.next_game is None


def test_an_unfilled_slot_is_named_after_the_series_that_fills_it():
    bracket = B.build(_payload())
    ds = bracket.by_slug("alds-a")
    assert ds.high.short == "Rays" and ds.high.seed == 1
    assert ds.low.placeholder and ds.low.label == "Yankees–Red Sox winner"
    assert ds.low.compact_label == "NYY/BOS winner"
    # Both pennant slots open: which feeder lands where is not known, so neither is named.
    cs = bracket.by_slug("alcs")
    assert cs.high.label == cs.low.label == "To be decided"


def test_each_wild_card_series_sits_beside_the_division_series_it_feeds():
    bracket = B.build(_payload())
    assert [s.slug for s in bracket.round("F", "AL")] == ["al-wild-card-b", "al-wild-card-a"]
    assert [s.slug for s in bracket.round("D", "AL")] == ["alds-a", "alds-b"]


def test_a_sentinel_small_hours_start_reads_as_time_not_set():
    cs = B.build(_payload()).by_slug("alcs")
    assert cs.games[0].time_tbd
    assert not B.build(_payload()).by_slug("alds-b").games[0].time_tbd


# --- one game in its series ----------------------------------------------------------

def test_a_preview_reads_the_series_going_into_the_game():
    info = B.game_in_series(B.build(_payload()), 2)
    assert info.standing == "Yankees lead 1-0"
    assert info.stakes == "Elimination game"
    assert info.game_line == "Game 2 of 3" and info.round_name == "AL Wild Card Series"
    assert info.seeds == {"147": 4, "111": 5}


def test_a_final_reads_the_series_after_it():
    nyy, bos = _team("NYY"), _team("BOS")
    games = [
        _game(1, 1, 3, bos, nyy, desc="AL Wild Card 'B'", state="final", winner="home"),
        _game(2, 2, 3, bos, nyy, desc="AL Wild Card 'B'", state="final", winner="away"),
        _game(3, 3, 3, bos, nyy, desc="AL Wild Card 'B'"),
    ]
    bracket = B.build(_payload(wc_b_games=games))
    assert B.game_in_series(bracket, 2).standing == "Series tied 1-1"
    assert B.game_in_series(bracket, 2).stakes is None
    decider = B.game_in_series(bracket, 3)
    assert decider.standing == "Series tied 1-1"
    assert decider.stakes == "Winner takes the series"


def test_a_game_behind_an_unfinished_one_claims_no_stakes():
    # Tomorrow's Game 3 while tonight's Game 2 is live: whether it is even played depends
    # on a result nobody has.
    info = B.game_in_series(B.build(_payload()), 6)
    assert not info.settled
    assert info.stakes is None
    assert info.if_necessary
    assert info.standing == "White Sox lead 1-0"


# --- when the bracket is the page -----------------------------------------------------

def test_the_bracket_replaces_the_race_only_once_the_field_is_set():
    assert B.is_active(B.build(_payload()))
    payload = _payload()
    payload["series"][0]["games"][0]["away_placeholder"] = True
    assert not B.is_active(B.build(payload))
    assert not B.is_active(None)


def test_last_seasons_bracket_is_not_this_seasons(tmp_path):
    from src import mlb_postseason

    db = tmp_path / "t.db"
    mlb_postseason.store({**_payload(), "season": 2025}, date(2025, 10, 30), db)
    assert B.load(date(2026, 9, 1), db) is None
    mlb_postseason.store(_payload(), date(2026, 9, 30), db)
    assert B.load(date(2026, 9, 30), db) is not None
    # A page built for an earlier day never reads a later snapshot.
    assert B.load(date(2026, 9, 29), db) is None


def test_duplicate_series_urls_fail_the_build():
    payload = _payload()
    payload["series"].append({**payload["series"][0], "series_id": "F_9"})
    with pytest.raises(ValueError):
        B.build(payload)


# --- surfaces ------------------------------------------------------------------------

def _hero(**kw):
    from domain.mlb_game_page import MLBGameHero

    base = dict(away_logo_url=None, home_logo_url=None, scheduled_time="", venue=None,
                game_status=None, probable_away_pitcher=None, probable_home_pitcher=None,
                probable_pitcher_status="unavailable", league_context="MLB")
    return MLBGameHero(**{**base, **kw})


def test_a_postseason_card_shows_the_seeds_and_who_leads_the_series():
    from components.game_cards import game_card_html
    from domain.models import SlateGame

    game = SlateGame(league="MLB", game_id="2", away_id="111", home_id="147",
                     away_short="Red Sox", home_short="Yankees", phase="postseason",
                     state="pre", series_game=2, series_total=3)
    info = B.game_in_series(B.build(_payload()), 2)
    html = game_card_html(game, "today", series=info)
    assert "AL Wild Card · Game 2 of 3" in html
    assert 'class="team-seed" title="No. 4 seed">4</span>Yankees' in html
    assert "Yankees lead 1-0" in html and "Elimination game" in html
    assert 'href="/playoffs/mlb/al-wild-card-b/"' in html


def test_without_a_bracket_the_card_falls_back_to_the_sources_line():
    from components.game_cards import game_card_html
    from domain.models import SlateGame

    game = SlateGame(league="MLB", game_id="2", phase="postseason", state="pre",
                     series_game=2, series_total=3, series_summary="NYY leads 1-0",
                     away_short="Red Sox", home_short="Yankees")
    assert "NYY leads 1-0" in game_card_html(game, "today")


def test_the_matchup_hero_trades_games_back_for_the_seed(monkeypatch):
    from domain.models import SlateGame
    from web import games

    monkeypatch.setattr(B, "load", lambda *_a, **_k: B.build(_payload()))
    hero = _hero(away_team="Boston Red Sox", home_team="New York Yankees",
                       away_standing="87-75 · 3rd in AL East, 11 GB",
                       home_standing="93-68 · 2nd in AL East, 4.5 GB",
                       home_form_note="Bats heating up")
    game = SlateGame(league="MLB", game_id="2", away_id="111", home_id="147",
                     phase="postseason")
    hero, series = games._postseason_hero(game, hero, date(2026, 9, 30))
    assert hero.away_standing == "No. 5 seed · 87-75 in the regular season"
    assert hero.home_form_note == "Regular-season form: bats heating up"
    assert "GB" not in hero.home_standing
    assert series["standing"] == "Yankees lead 1-0"
    assert series["href"] == "/playoffs/mlb/al-wild-card-b/"


def test_a_regular_season_hero_is_untouched():
    from domain.models import SlateGame
    from web import games

    hero = _hero(away_team="A", home_team="B", away_standing="80-70 · 2nd in AL East")
    out, series = games._postseason_hero(SlateGame(league="MLB", game_id="1",
                                                   phase="regular"), hero, date(2026, 8, 1))
    assert out is hero and series is None


def test_series_pages_are_exported():
    from web.management.commands.export_static import output_path, should_crawl

    assert should_crawl("/playoffs/mlb/alds-a/")
    assert str(output_path("/playoffs/mlb/alds-a/")) == "playoffs/mlb/alds-a/index.html"
