from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import Client

from domain.models import SlateGame
from web.games import find_game
from web.today import django_matchup_links


def game(league="MLB", game_id="401"):
    return SlateGame(
        league=league, game_id=game_id,
        away_name="Seattle Mariners", away_short="Mariners",
        home_name="Texas Rangers", home_short="Rangers",
    )


def test_shared_query_matchup_link_becomes_django_route():
    html = '<a href="?day=today&league=MLB&game=401">Matchup</a>'
    converted = django_matchup_links(html)
    assert 'href="/game/MLB/401/?day=today"' in converted


@patch("web.games.load_cached_schedules")
def test_game_resolution_uses_cached_slate(load):
    load.return_value = {"MLB": ([game()], object())}
    assert find_game("MLB", "401", date(2026, 8, 15)).home_display == "Rangers"
    assert find_game("MLB", "missing", date(2026, 8, 15)) is None


@patch("web.views.mlb_context")
@patch("web.views.find_game")
def test_mlb_endpoint_renders_existing_page_chunks(find, context):
    find.return_value = game()
    context.return_value = {
        "section": "today", "league": "MLB", "game": find.return_value,
        "slate_date": date(2026, 8, 15),
        "day": "today", "content_chunks": ["<div>Team Identity</div>"],
        "cache_source": "built", "build_ms": 12.5,
    }
    response = Client().get("/game/MLB/401/?day=today")
    assert response.status_code == 200
    assert b"Team Identity" in response.content
    assert b"favicons/mlb.svg" in response.content
    assert response["Server-Timing"] == "matchup;dur=12.5"


@patch("web.views.wnba_context")
@patch("web.views.find_game")
def test_wnba_endpoint_uses_wnba_page_context(find, context):
    find.return_value = game("WNBA", "w1")
    context.return_value = {
        "section": "today", "league": "WNBA", "game": find.return_value,
        "slate_date": date(2026, 8, 15), "day": "today",
        "content_chunks": ["<div>Game Snapshot</div>"],
        "cache_source": "database", "build_ms": 2.0,
    }
    response = Client().get("/game/WNBA/w1/?day=today")
    assert response.status_code == 200
    assert b"Game Snapshot" in response.content
    assert b"favicons/wnba.svg" in response.content
    assert response["X-Sports-Today-Cache"] == "database"
    context.assert_called_once()


@patch("web.views.mls_context")
@patch("web.views.find_game")
def test_mls_endpoint_uses_mls_page_context(find, context):
    find.return_value = game("MLS", "m1")
    context.return_value = {
        "section": "today", "league": "MLS", "game": find.return_value,
        "slate_date": date(2026, 8, 15), "day": "today",
        "content_chunks": ["<div>Tactical Matchup</div>"],
        "cache_source": "database", "build_ms": 1.8,
    }
    response = Client().get("/game/MLS/m1/?day=today")
    assert response.status_code == 200
    assert b"Tactical Matchup" in response.content
    assert b"favicons/mls.svg" in response.content
    assert response["X-Sports-Today-Cache"] == "database"
    context.assert_called_once()


@patch("services.nfl_bridge.feed_game_id", return_value="45904-DAL@PHI")
@patch("web.views.find_game")
def test_live_nfl_route_bridges_to_archive_matchup(find, _feed_id):
    find.return_value = game("NFL", "espn-1")
    response = Client().get("/game/NFL/espn-1/?day=today")
    assert response.status_code == 302
    assert response.url == "/nfl/game/45904-DAL@PHI/"


@patch("web.views.find_game", return_value=None)
def test_unknown_game_is_404(_find):
    assert Client().get("/game/MLB/missing/").status_code == 404


# --- postseason pages: two layers, retired sections (decision log 2026-09-30) -----------

def _fake_page():
    from domain.mlb_game_page import MLBGameHero, MLBGamePage, MLBTeamIdentity

    hero = MLBGameHero(away_team="Chicago Cubs", home_team="San Diego Padres",
                       away_logo_url=None, home_logo_url=None, scheduled_time="",
                       venue=None, game_status=None, probable_away_pitcher=None,
                       probable_home_pitcher=None, probable_pitcher_status="unavailable",
                       league_context="MLB")
    empty = MLBTeamIdentity("", None, "—", "", (), "", (), (), "")
    return MLBGamePage(hero=hero, game_story=(), away_identity=empty, home_identity=empty,
                       key_matchups=(), heating_up=(), cooling_off=(), opportunities=(),
                       game_shape=None, storylines=(), data_status=None,
                       generated_at="", as_of="2026-09-30")


def _page_text(monkeypatch, phase):
    from domain.models import SlateGame
    from web import games

    monkeypatch.setattr(games.matchup_cache, "load", lambda *a, **k: _fake_page())
    monkeypatch.setattr(games.cache, "get", lambda *a, **k: None)
    monkeypatch.setattr(games.cache, "set", lambda *a, **k: None)
    monkeypatch.setattr(games, "_postseason_sections",
                        lambda *a: ('<section class="pd">DESK</section>', ()))
    monkeypatch.setattr(games, "_postseason_hero", lambda g, hero, d: (hero, None))
    game = SlateGame(league="MLB", game_id="849842", phase=phase,
                     away_name="Chicago Cubs", home_name="San Diego Padres")
    return "".join(games.mlb_context(game, date(2026, 9, 30))["content_chunks"])


def test_a_postseason_page_is_two_layers_without_the_retired_sections(monkeypatch):
    text = _page_text(monkeypatch, "postseason")
    assert text.index("DESK") < text.index("Game Analysis")
    assert "Players Positioned to Succeed" not in text


def test_a_regular_season_page_is_unchanged(monkeypatch):
    text = _page_text(monkeypatch, "regular")
    assert "DESK" not in text and "Game Analysis" not in text
    assert "Players Positioned to Succeed" in text
