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


# --- schedule collapse toggle (Today page) ---
from components.date_switch import date_switch_html
from components.game_cards import games_toggle_html


def test_date_switch_is_sticky_when_collapsed():
    plain = date_switch_html("today", games_collapsed=False)
    assert "games=off" not in plain                         # default carries nothing
    sticky = date_switch_html("today", games_collapsed=True)
    assert 'href="?day=today&games=off"' in sticky          # Today keeps collapse
    assert 'href="?day=tomorrow&games=off"' in sticky       # Tomorrow keeps collapse


def test_games_toggle_expanded_offers_collapse():
    html = games_toggle_html("today", collapsed=False, count=15)
    assert 'href="?day=today&games=off"' in html and "Hide games" in html


def test_games_toggle_collapsed_offers_expand_with_count():
    html = games_toggle_html("tomorrow", collapsed=True, count=15)
    assert 'href="?day=tomorrow"' in html                    # expand drops the param
    assert "games=off" not in html
    assert "Show 15 games" in html


def test_games_toggle_singular():
    assert "Show 1 game ▾" in games_toggle_html("today", collapsed=True, count=1)
