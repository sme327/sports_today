"""The NFL archive as a running page, not just its builder.

`?view=nfl` was the one NFL surface verified only through `build_nfl_game_page` — the
route, the season/week pills and the matchup hand-off were never exercised together, so a
broken query-param contract or a renderer signature change would ship green.

These drive the real app through Streamlit's `AppTest`. They deliberately assert
*robustness* rather than specific content: the archive reads whatever seasons happen to be
ingested on this machine, and a test that demands 2025 be present would fail on a fresh
clone for the wrong reason. What must always hold is that the page renders, and that with
no data it says so plainly instead of raising.
"""

from __future__ import annotations

import pytest

from services.nfl_game_page import list_games, list_seasons, list_weeks

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

_TIMEOUT = 30


def _run(**params):
    at = AppTest.from_file("app.py", default_timeout=_TIMEOUT)
    at.query_params.update({"view": "nfl", **params})
    return at.run()


def test_the_archive_route_renders_without_raising():
    at = _run()
    assert not at.exception, f"?view=nfl raised: {at.exception}"
    text = " ".join(m.value for m in at.markdown) + " ".join(i.value for i in at.info)
    # Either the browser or the honest empty state — never a blank page.
    assert "NFL" in text


def test_with_no_seasons_loaded_it_says_so_rather_than_failing():
    """Guards the fresh-clone path: the archive is the first thing a new machine hits
    after `?view=nfl`, and an empty DB must produce guidance, not a traceback."""
    at = _run()
    if list_seasons():
        pytest.skip("this machine has NFL seasons loaded; empty-state path not exercised")
    assert not at.exception
    assert any("import_nfl_feed" in i.value for i in at.info)


@pytest.mark.skipif(not list_seasons(), reason="no NFL seasons ingested on this machine")
def test_browsing_a_week_lists_that_weeks_games():
    season = list_seasons()[0]
    weeks = list_weeks(season)
    assert weeks, "a loaded season must expose at least one week"
    week = int(weeks[0]["week"])
    at = _run(season=str(season), wk=str(week))
    assert not at.exception
    games = list_games(week, season)
    assert games, "a listed week must have games"
    body = " ".join(m.value for m in at.markdown)
    # The week's games reach the page — checked by team name, since ids are internal.
    first = games[0]
    team = str(first.get("home") or first.get("team") or "")
    if team:
        assert team.split()[-1] in body


@pytest.mark.skipif(not list_seasons(), reason="no NFL seasons ingested on this machine")
def test_opening_a_matchup_from_the_archive_renders_the_deep_dive():
    """The hand-off the builder tests cannot see: `?view=nfl&game=<feed id>` has to reach
    `build_nfl_game_page` and render, with a route back to the season."""
    season = list_seasons()[0]
    week = int(list_weeks(season)[0]["week"])
    games = list_games(week, season)
    game_id = str(games[0]["game_id"])
    at = _run(game=game_id)
    assert not at.exception, f"opening {game_id} raised: {at.exception}"
    body = " ".join(m.value for m in at.markdown)
    assert "Back to the season" in body


@pytest.mark.skipif(not list_seasons(), reason="no NFL seasons ingested on this machine")
def test_an_unknown_game_id_is_reported_not_raised():
    at = _run(game="no-such-game")
    assert not at.exception
    assert any("could not be found" in e.value for e in at.error)
