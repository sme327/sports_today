from unittest.mock import patch

from django.test import Client


@patch("web.views.archive_context")
def test_nfl_archive_endpoint(context):
    context.return_value = {
        "section": "nfl", "seasons": [2025], "season": 2025, "week": 1,
        "weeks": [{"week": 1, "label": "Wk 1"}],
        "games": [{"game_id": "g1", "away": "Bills", "home": "Jets",
                   "away_score": 24, "home_score": 17}],
    }
    response = Client().get("/nfl/")
    assert response.status_code == 200
    assert b"NFL" in response.content and b"Bills" in response.content
    assert b'/nfl/game/g1/' in response.content


@patch("web.views.matchup_context")
def test_nfl_matchup_endpoint(context):
    context.return_value = {
        "section": "nfl",
        "page": type("Page", (), {"hero": type("Hero", (), {
            "away": "Bills", "home": "Jets"
        })()})(),
        "content": "<div>Team identity</div>",
        "cache_source": "database", "build_ms": 1.4,
    }
    response = Client().get("/nfl/game/g1/")
    assert response.status_code == 200
    assert b"Team identity" in response.content
    assert b"favicons/nfl.svg" in response.content
    assert response["Server-Timing"] == "matchup;dur=1.4"
    assert response["X-Sports-Today-Cache"] == "database"


@patch("web.views.matchup_context", return_value=None)
def test_unknown_nfl_matchup_is_404(_context):
    assert Client().get("/nfl/game/missing/").status_code == 404


@patch("web.views.render")
@patch("web.nfl.pregame_context")
@patch("services.nfl_bridge.feed_game_id", return_value=None)
@patch("web.views.find_game")
def test_an_upcoming_nfl_game_renders_a_pregame_page(find, _feed, pregame, render):
    """The feed holds only played games, so an upcoming game never matches it; the
    pregame path is what serves a matchup page before kickoff — all season, and at
    week 1 from last season's aggregates, labeled."""
    from django.http import HttpResponse
    from domain.models import SlateGame

    find.return_value = SlateGame(
        league="NFL", game_id="401999", away_name="San Francisco 49ers",
        home_name="Philadelphia Eagles", away_short="49ers", home_short="Eagles",
        phase="regular", season=2026, week=1)
    pregame.return_value = {"section": "nfl", "page": object(), "content": "<div>x</div>",
                            "pregame": True, "cache_source": "built", "build_ms": 3.0}
    render.return_value = HttpResponse(b"ok")
    response = Client().get("/game/NFL/401999/")
    assert response.status_code == 200
    assert pregame.called
    assert render.call_args[0][2]["pregame"] is True
