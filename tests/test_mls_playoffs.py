"""The MLS playoff race, written as the ways it could overclaim.

Clinched and out are arithmetic and must never arrive early; the field is cut at seventh
and ninth because that is the format the source states; and the page describes, it does not
project. No network.
"""

from __future__ import annotations

from datetime import date

from services import mls_playoffs as M


def _club(i, points, played=27, conference="Eastern Conference", rank=None, w=None, d=0, l=0):
    return M.Club(team_id=str(i), name=f"Club {i}", abbr=None, logo=None, conference=conference,
                  rank=rank or i, points=points, played=played,
                  wins=w if w is not None else points // 3, draws=d, losses=l, goal_difference=0)


def _conference(points_list, played=27):
    return [_club(i, p, played=played) for i, p in enumerate(points_list, 1)]


# --- arithmetic ------------------------------------------------------------------------

def test_reach_is_points_plus_three_a_game_left():
    assert _club(1, 40, played=30).reach == 40 + 3 * 4


def test_clinched_counts_a_tie_against_the_club():
    # Club 1 on 60; five others can still reach 60 or more, so at worst it finishes sixth
    # — clinched for Round One. Six able to reach it still leaves seventh. A seventh club
    # able only to *tie* (39 + 21 = 60) is enough to take it away, because a tie counts
    # against the club: the league's tiebreakers could put it eighth.
    table = _conference([60, 46, 46, 43, 42, 39, 34, 33, 33, 30, 29, 29, 27, 24, 20])
    assert M.clinched(table[0], table, M.ROUND_ONE)
    six = list(table)
    six[6] = _club(7, 39)
    assert M.clinched(six[0], six, M.ROUND_ONE)
    seven = list(six)
    seven[7] = _club(8, 39)
    assert not M.clinched(seven[0], seven, M.ROUND_ONE)


def test_out_only_when_enough_clubs_are_already_beyond_reach():
    table = _conference([60, 50, 50, 50, 50, 50, 50, 50, 50, 20], played=33)
    last = table[-1]                # 20 + 3 = 23: nine clubs already above it
    assert M.eliminated(last, table, M.FIELD)
    # If ninth were on exactly its reach, a tie is still possible — not out.
    level = list(table)
    level[8] = _club(9, 23, played=33)
    assert not M.eliminated(level[-1], level, M.FIELD)


def test_window_reads_games_played_not_wins_and_losses():
    assert M.window_state([]) == "preseason"
    assert M.window_state(_conference([0] * 3, played=0)) == "preseason"
    assert M.window_state(_conference([30] * 3, played=20)) == "early"
    assert M.window_state(_conference([30] * 3, played=27)) == "live"
    assert M.window_state(_conference([30] * 3, played=34)) == "final"


# --- the table ---------------------------------------------------------------------------

def test_the_field_is_cut_at_seventh_and_ninth_in_each_conference():
    east = _conference([60, 46, 46, 43, 42, 39, 34, 33, 33, 33, 30, 29, 29, 27, 24])
    west = [_club(100 + i, p, conference="Western Conference", rank=i)
            for i, p in enumerate([50, 47, 47, 45, 44, 41, 38, 36, 36, 32, 32, 32, 31, 29, 21], 1)]
    panels, status = M.race(east + west)
    assert [p["name"] for p in panels] == ["Eastern race", "Western race"]
    e = panels[0]
    assert len(e["field"]) == 7 and len(e["wildcard"]) == 2
    assert [r["seed"] for r in e["wildcard"]] == [8, 9]
    assert status["8"]["in_field"] and not status["10"]["in_field"]


def test_the_order_is_the_stored_rank_not_a_resort_on_points():
    # Three clubs on 33: the source's tiebreakers put 8 above 9 above 10. Reversing their
    # ranks must reverse the rows, proving the page never re-sorts on points.
    table = _conference([60, 46, 46, 43, 42, 39, 34, 33, 33, 33, 30, 29, 29, 27, 24])
    swapped = [M.Club(**{**c.__dict__, "rank": {8: 10, 10: 8}.get(c.rank, c.rank)}) for c in table]
    panels, _ = M.race(swapped)
    assert panels[0]["wildcard"][0]["name"] == "Club 10"


def test_level_points_are_worded_as_level():
    table = _conference([60, 46, 46, 43, 42, 39, 34, 33, 33, 33, 30, 29, 29, 27, 24])
    panels, _ = M.race(table)
    assert "level with 10th on points" in panels[0]["wildcard"][0]["status"]
    assert panels[0]["bubble"][0]["status"].startswith("level with 9th on points")


def test_an_empty_chase_says_which_kind_of_empty_it_is():
    table = _conference([70, 68, 66, 64, 62, 60, 58, 56, 54, 10, 9, 8], played=33)
    panels, _ = M.race(table)
    assert panels[0]["bubble"] == []
    assert "mathematically out" in panels[0]["note"]
    assert "Club 10" in panels[0]["out"]


# --- games that matter -------------------------------------------------------------------

def _fixture(away, home, day="2026-10-10T19:30Z"):
    return {"game_id": f"{away}-{home}", "game_date": day, "away_id": str(away), "home_id": str(home),
            "away_short": f"Club {away}", "home_short": f"Club {home}", "state": "pre"}


def test_a_meeting_of_two_clubs_at_the_line_is_a_six_pointer():
    table = _conference([60, 46, 46, 43, 42, 39, 34, 33, 33, 33, 30, 29, 29, 27, 24])
    _, status = M.race(table)
    games = M._important([_fixture(9, 10), _fixture(1, 15)], status)
    assert games and games[0]["away"] == "Club 9"
    assert games[0]["why"].startswith("A six-pointer at the line")
    assert "Eastern Conference" in games[0]["why"]


def test_a_game_between_clubs_already_out_never_counts():
    table = _conference([70, 68, 66, 64, 62, 60, 58, 56, 54, 10, 9, 8], played=33)
    _, status = M.race(table)
    assert M._important([_fixture(10, 11)], status) == []


def test_the_context_reads_no_odds_and_states_the_format(tmp_path):
    ctx = M.build_context(date(2026, 10, 2), db_path=tmp_path / "missing.db",
                          fixture_fetcher=lambda *a: [])
    assert ctx["window"] == "preseason" and not ctx["has_data"]
    assert ctx["format_note"] == "Places 1-7 go to Round One; 8-9 play the Wild Card matches"
    assert ctx["record_label"] == "Points"
    source = (M.__file__ and open(M.__file__).read()).lower()
    for word in ("odds", "spread", "moneyline", "probability"):
        assert word not in source.replace("not playoff odds", ""), word
