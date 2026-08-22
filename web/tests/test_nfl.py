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


@patch("web.views.matchup_context")
@patch("services.nfl_bridge.last_meeting_game_id", return_value="46033-SFO@PHI")
@patch("services.nfl_bridge.feed_game_id", return_value=None)
@patch("web.views.find_game")
def test_preseason_game_shows_last_meeting_with_banner(find, _feed, _meeting, context):
    """A feed-uncovered NFL game (preseason always) renders the pairing's most recent
    archived meeting at the slate game's own URL, with a banner saying exactly that —
    never a bare redirect that would pass the old game off as tonight's."""
    from domain.models import SlateGame

    find.return_value = SlateGame(
        league="NFL", game_id="401999", away_name="San Francisco 49ers",
        home_name="Philadelphia Eagles", away_short="49ers", home_short="Eagles",
        phase="preseason", season=2026)
    context.return_value = {
        "section": "nfl",
        "page": type("Page", (), {"hero": type("Hero", (), {
            "away": "49ers", "home": "Eagles"})()})(),
        "content": "<div>Team identity</div>",
        "cache_source": "database", "build_ms": 2.0,
    }
    response = Client().get("/game/NFL/401999/")
    assert response.status_code == 200
    assert b"Preseason preview" in response.content
    assert b"most recent real\nmeeting" in response.content or b"most recent real" in response.content
    assert b"Team identity" in response.content
    context.assert_called_once_with("46033-SFO@PHI")


@patch("services.nfl_bridge.last_meeting_game_id", return_value=None)
@patch("services.nfl_bridge.feed_game_id", return_value=None)
@patch("web.views.find_game")
def test_preseason_game_with_no_archived_meeting_falls_back_to_simple_page(find, _f, _m):
    from domain.models import SlateGame

    find.return_value = SlateGame(
        league="NFL", game_id="401998", away_name="A", home_name="B",
        away_short="A", home_short="B", phase="preseason", season=2026)
    response = Client().get("/game/NFL/401998/")
    assert response.status_code == 200
    assert b"Preseason preview" not in response.content
