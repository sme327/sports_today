from components.navigation import back_href, game_href, day_label, day_possessive
from domain.models import SlateGame


def test_game_href_encodes_same_tab_params():
    game = SlateGame(league="World Cup", game_id="wc-1")
    href = game_href("tomorrow", game)
    assert href.startswith("?")
    assert "day=tomorrow" in href
    assert "league=World+Cup" in href  # space encoded, stays a query param
    assert "game=wc-1" in href


def test_back_href_only_carries_day():
    assert back_href("today") == "?day=today"
    assert "game=" not in back_href("today")


def test_day_labels():
    assert day_label("tomorrow") == "Tomorrow"
    assert day_label("today") == "Today"
    assert day_possessive("today").startswith("Today")
