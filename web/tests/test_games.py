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
        "section": "today", "game": find.return_value, "slate_date": date(2026, 8, 15),
        "day": "today", "content_chunks": ["<div>Team Identity</div>"],
        "cache_source": "built", "build_ms": 12.5,
    }
    response = Client().get("/game/MLB/401/?day=today")
    assert response.status_code == 200
    assert b"Team Identity" in response.content
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
    assert response["X-Sports-Today-Cache"] == "database"
    context.assert_called_once()


@patch("web.views.find_game", return_value=None)
def test_unknown_game_is_404(_find):
    assert Client().get("/game/MLB/missing/").status_code == 404
