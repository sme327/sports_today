"""Editorial signals for leagues without player props.

These guard the honesty rules more than the arithmetic: a record gap describes the
past and must never be dressed as a forecast, a league that publishes no records must
produce no claims, and a game that scores well must be able to say why.
"""

from __future__ import annotations

from domain.models import SlateGame
from services import editorial
from services.editorial import (
    MIN_GAMES, best_game, interest, parse_record, rank_games,
)


def _g(away_rec=None, home_rec=None, *, away_rank=None, home_rank=None,
       away="Away", home="Home", **kw) -> SlateGame:
    return SlateGame(league="NFL", game_id="g", away_short=away, home_short=home,
                     away_record=away_rec, home_record=home_rec,
                     away_rank=away_rank, home_rank=home_rank, **kw)


def _kinds(game: SlateGame) -> set[str]:
    return {s.kind for s in interest(game).signals}


# --- reading a record --------------------------------------------------------

def test_parses_wins_losses_and_ties():
    s = parse_record("9-0-1")
    assert (s.wins, s.losses, s.ties, s.games) == (9, 0, 1, 10)
    assert s.win_pct == 0.95            # a tie counts as half


def test_missing_or_unparseable_record_is_empty_not_zero():
    for value in (None, "", "TBD", "n/a"):
        s = parse_record(value)
        assert s.win_pct is None, value  # never 0.000, which would read as "terrible"


def test_win_pct_withheld_until_the_sample_is_real():
    assert parse_record("3-0").win_pct is None          # 3 games < MIN_GAMES
    assert parse_record("2-2").win_pct is not None      # 4 games == MIN_GAMES
    assert MIN_GAMES == 4


# --- the signals -------------------------------------------------------------

def test_two_strong_teams_are_a_marquee_matchup():
    assert "marquee" in _kinds(_g("8-1", "9-1"))


def test_the_broad_middle_still_gets_an_explanation():
    """A 6-5 vs 8-3 game is ordinary but watchable; before this existed such games
    scored in the 70s and offered no reason at all."""
    assert "solid" in _kinds(_g("6-5", "8-3"))


def test_big_gap_with_the_weaker_side_at_home_is_an_upset_setup():
    kinds = _kinds(_g("9-2", "3-8"))          # strong visitor, weak host
    assert "upset_setup" in kinds and "mismatch" not in kinds


def test_big_gap_with_the_weaker_side_away_is_only_lopsided():
    kinds = _kinds(_g("3-8", "9-2"))          # weak visitor, strong host
    assert "mismatch" in kinds and "upset_setup" not in kinds


def test_upset_setup_carries_its_own_caveat():
    """The one signal that could be misread as a prediction must say it is not."""
    upset = next(s for s in interest(_g("9-2", "3-8")).signals if s.kind == "upset_setup")
    assert upset.caveats and "not tonight" in " ".join(upset.caveats)


def test_two_poor_teams_are_described_honestly_not_flattered():
    kinds = _kinds(_g("2-9", "3-8"))
    assert "struggling" in kinds
    assert "even" not in kinds and "marquee" not in kinds


def test_ranked_pair_does_not_repeat_a_rank_already_in_the_name():
    """College short names arrive pre-prefixed ("#7 BYU"); the signal adds its own."""
    g = _g("8-1", "9-1", away="#7 BYU", home="#8 Texas Tech", away_rank=7, home_rank=8)
    detail = next(s for s in interest(g).signals if s.kind == "ranked_pair").detail
    assert "#7 BYU" in detail and "#7 #7" not in detail


# --- scoring -----------------------------------------------------------------

def test_evenly_bad_does_not_outrank_evenly_good():
    """The regression that real data exposed: closeness alone scored highly, so two
    2-9 teams ranked near two 9-1 teams. Competitiveness is weighted by quality."""
    good = interest(_g("8-1", "9-1")).score
    bad = interest(_g("1-8", "2-8")).score
    assert bad < good / 2, (bad, good)


def test_every_scored_game_can_explain_itself():
    """No game may carry a meaningful score with nothing to justify it."""
    cases = [_g("8-1", "9-1"), _g("6-5", "8-3"), _g("9-2", "3-8"), _g("4-7", "7-4"),
             _g("2-9", "3-8"), _g("5-5", "5-5"), _g("1-8", "2-8")]
    for g in cases:
        detail = interest(g)
        assert detail.signals, f"{g.away_record} @ {g.home_record} scored {detail.score} silently"


def test_score_components_are_inspectable():
    detail = interest(_g("8-1", "9-1", conference_game=True, away_rank=7, home_rank=8))
    assert set(detail.components) == {"quality", "competitiveness", "rank", "stakes"}
    assert all(0.0 <= v <= 1.0 for v in detail.components.values())


def test_unknown_records_score_zero_rather_than_mid_table():
    """The NHL scoreboard publishes no records. Such a game must not be quietly
    ranked in the middle of the slate."""
    detail = interest(_g(None, None))
    assert detail.score == 0
    assert any("No team records" in c for c in detail.caveats)


def test_early_season_is_called_out_rather_than_scored():
    detail = interest(_g("1-0", "1-0"))
    assert detail.score == 0
    assert any("Too early" in c for c in detail.caveats)


def test_every_game_carries_the_missing_context_caveat():
    assert any("no injuries" in c for c in interest(_g("8-1", "9-1")).caveats)


# --- picking the slate's best -------------------------------------------------

def test_best_game_picks_the_strongest_and_ranking_is_ordered():
    games = [_g("2-9", "3-8", away="Bad", home="Worse"),
             _g("8-1", "9-1", away="Good", home="Great"),
             _g("6-5", "8-3", away="Ok", home="Fine")]
    ranked = rank_games(games)
    assert [g.away_short for g, _ in ranked] == ["Good", "Ok", "Bad"]
    pick = best_game(games)
    assert pick is not None and pick[0].away_short == "Good"


def test_best_game_is_none_when_nothing_deserves_it():
    """The app is allowed to say there is nothing worth highlighting."""
    assert best_game([_g("2-9", "3-8"), _g("1-8", "2-8")]) is None
    assert best_game([_g(None, None)]) is None
    assert best_game([]) is None


def test_ranking_keeps_unknown_games_in_the_slate():
    games = [_g(None, None, away="Unknown"), _g("8-1", "9-1", away="Known")]
    assert len(rank_games(games)) == 2          # complete slate, nothing dropped
    assert rank_games(games)[0][0].away_short == "Known"


# --- the deliberate omissions -------------------------------------------------

def test_module_does_not_consult_betting_odds():
    """The Vision rules odds out. If that ever changes it should be a product
    decision with a decision-log entry, not a quiet import."""
    source = (editorial.__file__)
    text = open(source).read()
    code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))
    body = code.split('"""', 2)[-1]              # skip the module docstring
    for token in ("odds", "spread", "moneyline", "favorite_line"):
        assert token not in body.lower(), f"{token!r} appears in editorial logic"
