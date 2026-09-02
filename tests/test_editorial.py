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


# --- comparing across sports ----------------------------------------------------

def _slate(league: str, pairs) -> list[SlateGame]:
    return [SlateGame(league=league, game_id=f"{league}{i}",
                      away_name=f"{league}A{i}", home_name=f"{league}H{i}",
                      away_record=a, home_record=h)
            for i, (a, h) in enumerate(pairs)]


# A tight league (baseball-like, everyone near .500) and a wide one (football-like).
_TIGHT = _slate("MLB", [("62-56", "56-62"), ("71-47", "47-71"),
                        ("60-58", "58-60"), ("65-53", "53-65")])
_WIDE = _slate("NFL", [("9-2", "2-9"), ("8-3", "3-8"), ("7-4", "4-7"), ("6-5", "5-6")])


def test_league_spread_is_measured_from_the_slate():
    from services.editorial import league_norms
    norms = league_norms(_TIGHT + _WIDE)
    assert norms["MLB"].sd < norms["NFL"].sd      # the artefact, quantified
    assert norms["MLB"].teams == 8 and norms["NFL"].teams == 8
    assert norms["MLB"].usable and norms["NFL"].usable


def test_a_league_with_too_few_teams_is_not_normalised():
    """Two teams say nothing about their league's spread."""
    from services.editorial import league_norms
    norms = league_norms(_slate("MLS", [("10-4", "4-10")]))
    assert norms["MLS"].teams == 2 and not norms["MLS"].usable
    assert norms["MLS"].strength(0.7) is None


def test_dominant_teams_in_different_sports_score_alike():
    """The whole point: a .620 baseball team and a .818 football team are both about
    as far ahead of their league, so they must not be ranked by their sport's
    schedule length."""
    from services.editorial import league_norms
    norms = league_norms(_TIGHT + _WIDE)
    mlb_top = norms["MLB"].strength(71 / 118)
    nfl_top = norms["NFL"].strength(9 / 11)
    assert abs(mlb_top - nfl_top) < 0.15, (mlb_top, nfl_top)


def test_normalising_does_not_reorder_within_a_league():
    """It fixes cross-sport comparison; it must not disturb rankings inside a sport."""
    from services.editorial import rank_games
    raw = [g.game_id for g, _ in rank_games(_TIGHT)]
    mixed = [g.game_id for g, _ in rank_games(_TIGHT + _WIDE) if g.league == "MLB"]
    assert raw == mixed


def test_cross_league_claims_are_gated_on_having_enough_teams():
    from services.editorial import cross_league_comparable
    assert cross_league_comparable(_TIGHT + _WIDE)
    thin = _TIGHT + _slate("MLS", [("10-4", "4-10")])
    assert not cross_league_comparable(thin)


def test_interest_without_a_norm_is_unchanged():
    """Callers that score a single game still get the within-league answer."""
    game = _TIGHT[1]
    assert interest(game).score == interest(game, None).score


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


# --- home court is a claim that has to be earned ---------------------------------

def _home_split(away_rec, home_rec, home_at_home, **kw):
    return SlateGame(league="WNBA", game_id="g", away_short="Road", home_short="Host",
                     away_record=away_rec, home_record=home_rec,
                     home_home_record=home_at_home, **kw)


def test_home_edge_compares_home_form_to_the_team_s_own_overall():
    from services.editorial import home_edge
    assert home_edge(_home_split("20-10", "12-19", "9-6")) > 0     # better at home
    assert home_edge(_home_split("20-10", "12-19", "5-10")) < 0    # worse at home
    assert home_edge(_home_split("20-10", "12-19", None)) is None  # not published
    assert home_edge(_home_split("20-10", "12-19", "1-1")) is None # too few home games


def test_upset_setup_needs_the_host_to_be_good_at_home():
    """Observed live: a 12-19 side hosting was framed as an upset setup while going
    5-10 at home — worse than their own overall — and they lost by 6."""
    real_edge = _home_split("23-9", "12-19", "9-6")
    assert "upset_setup" in _kinds(real_edge)
    no_edge = _home_split("23-9", "12-19", "5-10")
    kinds = _kinds(no_edge)
    assert "upset_setup" not in kinds and "mismatch" in kinds


def test_the_home_record_is_shown_either_way():
    """Whether it supports the angle or undercuts it, the reader sees the number."""
    for host_home in ("9-6", "5-10"):
        g = _home_split("23-9", "12-19", host_home)
        ev = " ".join(e for s in interest(g).signals for e in s.evidence)
        assert f"{host_home} at home" in ev, (host_home, ev)


def test_a_missing_split_does_not_veto_the_upset_angle():
    """Absent data is not evidence against. Leagues that publish no splits keep the
    old behaviour rather than silently losing the signal."""
    assert "upset_setup" in _kinds(_home_split("23-9", "12-19", None))


# --- what earns a chip on the card ---------------------------------------------

def test_upset_setup_needs_the_favourite_to_actually_be_good():
    """A 5-6 side hosting an 8-3 side is not an upset story. Without this gate the
    label fired on 10 of 45 college games and stopped meaning anything."""
    weak_favourite = _g("8-3", "5-6")        # .727 vs .455 — gap is wide enough…
    assert "upset_setup" not in _kinds(weak_favourite)   # …but .727 is not strong
    real = _g("9-2", "4-7")                  # .818 favourite, weak host
    assert "upset_setup" in _kinds(real)


def test_evenly_matched_alone_does_not_earn_a_card_chip():
    """Without a norm, "even" falls back to an absolute .500 bar — and .508 vs .517 is
    the most ordinary pairing in baseball, not a reason to watch. The game page can
    show it with its evidence; a chip has no room to qualify itself."""
    from services.editorial import card_signal
    ordinary = _g("60-58", "61-57")          # a typical mid-table baseball pairing
    assert "even" in _kinds(ordinary)        # still true, and still on the game page
    assert card_signal(ordinary) is None     # but not shouted on an un-normalised card


def test_evenly_matched_earns_a_chip_once_the_league_can_be_judged():
    """With a norm, "even" means close *and* good against this league — which fired on
    31 of 191 MLB games at a 2.84 mean margin against a 3.39 base."""
    from services.editorial import card_signal, league_norms
    slate = _lg("MLB", [("72-46", "70-48"),   # two of the league's best, close
                        ("60-58", "61-57"), ("59-59", "58-60"), ("45-73", "44-74")])
    norm = league_norms(slate).get("MLB")
    top = card_signal(slate[0], norm)
    assert top is not None and top.kind in ("marquee", "even")
    assert card_signal(slate[1], norm) is None   # mid-table stays quiet


def test_card_chip_appears_for_the_genuinely_notable():
    from services.editorial import card_signal
    for game in (_g("9-1", "8-2"),                                   # marquee
                 _g("9-2", "4-7"),                                   # upset setup
                 _g("6-3", "7-2", away_rank=3, home_rank=8)):        # ranked pair
        assert card_signal(game) is not None


def test_card_chip_is_absent_when_records_are_unknown():
    from services.editorial import card_signal
    assert card_signal(_g(None, None)) is None


# --- rendering ----------------------------------------------------------------

def test_render_shows_records_even_when_the_lead_is_rank_based():
    """A rank-led signal carries only "#1 Team" as evidence; the records come from
    the quality signals and must not be dropped."""
    from components.editorial import editorial_html
    g = _g("9-0", "2-8", away="#1 Ohio State", home="Purdue", away_rank=1)
    html = editorial_html(interest(g))
    assert "Ohio State 9-0" in html and "Purdue 2-8" in html


def test_render_gives_caveats_the_same_block_treatment_as_evidence():
    """Product rule: negative evidence is at least as prominent as supporting
    evidence. Both must use the same evidence block, inside the same grid."""
    from components.editorial import editorial_html
    html = editorial_html(interest(_g("9-2", "3-8")))
    assert html.count('class="op-evidence') >= 2
    assert 'op-evidence op-flat' in html          # caveat, same primitive
    assert 'op-evidence op-good' in html          # evidence, same primitive
    assert "no injuries" in html


def test_render_is_empty_when_there_is_nothing_honest_to_say():
    from components.editorial import editorial_html
    assert editorial_html(interest(_g(None, None))) == ""


def test_empty_state_names_the_league_and_the_reason():
    from components.editorial import editorial_empty_html
    html = editorial_empty_html("NHL", "No team records published for this league.")
    assert "NHL" in html and "No team records" in html


def test_render_escapes_team_names():
    from components.editorial import editorial_html
    g = _g("9-1", "8-2", away="<script>x</script>", home="Home")
    assert "<script>" not in editorial_html(interest(g))


# --- the deliberate omissions -------------------------------------------------

def test_module_does_not_consult_betting_odds():
    """The Vision rules odds out. If that ever changes it should be a product
    decision with a decision-log entry, not a quiet import.

    Checks the parsed code — names, attributes and string literals — rather than the
    raw text, so the module stays free to *discuss* odds in its docstrings (it
    explains at length why they are excluded) and to use "spread" in its statistical
    sense without tripping the guard.
    """
    import ast

    tree = ast.parse(open(editorial.__file__).read())
    for node in ast.walk(tree):                       # drop every docstring
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and body:
            first = body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                body.pop(0)

    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            used.add(node.attr.lower())
        elif isinstance(node, ast.arg):
            used.add(node.arg.lower())
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            used.add(node.name.lower())
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            used.add(node.value.lower())

    for token in ("odds", "moneyline", "point_spread", "vegas", "sportsbook"):
        offenders = [u for u in used if token in u]
        assert not offenders, f"{token!r} reached the editorial logic via {offenders}"


# --- naming a best game, honestly ------------------------------------------------

def _lg(league, pairs):
    return [SlateGame(league=league, game_id=f"{league}{i}",
                      away_name=f"{league}A{i}", home_name=f"{league}H{i}",
                      away_short=f"A{i}", home_short=f"H{i}",
                      away_record=a, home_record=h)
            for i, (a, h) in enumerate(pairs)]


_FULL = _lg("MLB", [("71-47", "66-52"), ("60-58", "58-60"), ("52-67", "71-47"),
                    ("64-53", "56-63"), ("57-61", "58-61")])


def test_best_game_refuses_a_cross_league_claim_it_cannot_support():
    """The guard existed but callers had to remember it, which is not a guard. On a
    real slate the WNBA had four teams playing — far too few to normalise — and
    best_game still returned a pick."""
    from services.editorial import best_game
    thin = _lg("WNBA", [("20-10", "10-20")])          # 2 teams: not normalisable
    assert best_game(_FULL + thin) is None
    assert best_game(_FULL) is not None                # single league is always fair


def test_best_per_league_marks_each_league_separately():
    from services.editorial import best_per_league
    picks, unjudged = best_per_league(_FULL + _lg("WNBA", [("20-10", "10-20")]))
    assert set(picks) == {"MLB"}
    assert unjudged == ["WNBA"]


def test_a_league_that_cannot_be_judged_is_named_not_dropped():
    """So the UI can say why there is no pick, rather than silently omitting it."""
    from services.editorial import best_per_league
    _, unjudged = best_per_league(_lg("WNBA", [("20-10", "10-20")]))
    assert unjudged == ["WNBA"]


def test_no_pick_when_nothing_clears_the_bar():
    from services.editorial import best_per_league
    weak = _lg("MLB", [("40-78", "38-80"), ("41-77", "39-79"),
                       ("42-76", "40-78"), ("43-75", "41-77")])
    picks, _ = best_per_league(weak)
    assert picks == {}


def test_the_card_shows_the_chip_only_when_marked():
    from components.game_cards import game_card_html, schedule_grid_html
    g = _FULL[0]
    assert "bg-chip" in game_card_html(g, "today", is_best=True)
    assert "bg-chip" not in game_card_html(g, "today")
    grid = schedule_grid_html(_FULL, "today", best_ids={str(_FULL[0].game_id)})
    assert grid.count("bg-chip") == 1, "exactly one card marked"


def test_marquee_is_reachable_in_a_league_nobody_wins_650_in():
    """The bar used to be a raw .650. Baseball's best team finishes near .620, so
    "Marquee matchup" fired on **zero** of 191 finished MLB games — a label that could
    not exist all season. Judged against the league instead, its top pairings qualify."""
    from services.editorial import interest, league_norms, standings
    slate = _lg("MLB", [("74-44", "72-46"),                    # the league's two best
                        ("64-54", "62-56"), ("60-58", "58-60"),
                        ("54-64", "52-66"), ("46-72", "44-74")])
    norm = league_norms(slate).get("MLB")
    assert norm is not None and norm.usable
    assert max(s.win_pct for g in slate for s in standings(g)) < 0.650   # nobody clears it
    assert "marquee" in {s.kind for s in interest(slate[0], norm).signals}
    assert "marquee" not in {s.kind for s in interest(slate[2], norm).signals}


def test_even_needs_both_sides_good_not_merely_similar():
    """Measured over 191 MLB games, closeness of record predicted nothing: the old
    gap-only rule fired on 134 and its games averaged a *wider* margin than the rest.
    Quality is what predicts a close game, so both sides must clear a league-relative
    bar — and an absolute one, since on an all-poor slate the least-poor look strong."""
    from services.editorial import interest, league_norms
    slate = _lg("MLB", [("70-48", "69-49"),      # close and good
                        ("48-70", "47-71"),      # close and bad
                        ("60-58", "59-59"), ("62-56", "61-57"),
                        ("55-63", "54-64"), ("44-74", "43-75")])
    norm = league_norms(slate).get("MLB")
    kinds = lambda g: {s.kind for s in interest(g, norm).signals}
    assert "even" in kinds(slate[0])
    assert "even" not in kinds(slate[1])


# --- the market line is displayed, never consumed (2026-09-02) ------------------------

def test_the_interest_score_is_identical_with_and_without_a_market_line():
    """The behavioural half of the odds ban.

    NCAAF matchup pages now show a spread and total, because that page has the least to
    work with in the product and a college spread is the densest fact available about a
    forty-point mismatch. The AST guard above proves `editorial` never *names* odds; this
    proves it never *uses* them, which is the property that actually matters — a future
    signal could reach `game.meta` without writing the word.
    """
    import dataclasses

    base = _g("6-1", "5-2", away="East Carolina", home="Alabama")
    with_line = dataclasses.replace(base, meta={
        **(base.meta or {}),
        "market_line": {"detail": "ALA -28.5", "spread": -28.5, "total": 52.5,
                        "favourite": "ALA", "provider": "Draft Kings"},
    })

    plain, priced = interest(base), interest(with_line)
    assert plain.score == priced.score
    assert [s.kind for s in plain.signals] == [s.kind for s in priced.signals]
    assert [(s.label, s.detail) for s in plain.signals] == \
           [(s.label, s.detail) for s in priced.signals]
    assert [s.evidence for s in plain.signals] == [s.evidence for s in priced.signals]


def test_a_wildly_lopsided_line_still_moves_nothing():
    """A forty-point spread is the strongest statement a market makes. If odds were
    leaking into the score anywhere, this is the input that would expose it."""
    import dataclasses

    base = _g("1-0", "1-0", away="North Texas", home="Indiana")
    lopsided = dataclasses.replace(base, meta={
        **(base.meta or {}),
        "market_line": {"detail": "IU -40.5", "spread": -40.5, "total": 55.5,
                        "favourite": "IU", "provider": "Draft Kings"},
    })
    assert interest(base).score == interest(lopsided).score


def test_only_college_football_shows_a_line():
    """Scoped on purpose. On an MLB page a spread would sit beside props we score, and a
    reader would fairly read it as our endorsement of the market's view."""
    from web.simple_game import _MARKET_LINE_LEAGUES

    assert _MARKET_LINE_LEAGUES == {"NCAAF"}
