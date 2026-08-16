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
    assert response["Server-Timing"] == "matchup;dur=1.4"
    assert response["X-Sports-Today-Cache"] == "database"


@patch("web.views.matchup_context", return_value=None)
def test_unknown_nfl_matchup_is_404(_context):
    assert Client().get("/nfl/game/missing/").status_code == 404
