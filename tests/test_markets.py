"""Registry tests: canonical labels, round-trip resolve, grading rules, actual
display, and backward-compat resolution of the exact market strings already in the
ledger. Offline; no DB."""

from __future__ import annotations

import pytest

from domain import markets as M

# (key, threshold, direction, canonical text) — text must match what scorers emit.
CASES = [
    ("batter_hit", 1, "over", "1+ Hit"),
    ("sp_k", 7, "over", "7+ Strikeouts (SP)"),
    ("sp_k", 5, "under", "≤ 5 Strikeouts (SP)"),
    ("sp_hits", 6, "over", "6+ Hits Allowed (SP)"),
    ("sp_hits", 5, "under", "≤ 5 Hits Allowed (SP)"),
    ("wnba_points", 15, "over", "15+ Points"),
    ("wnba_rebounds", 6, "over", "6+ Rebounds"),
    ("wnba_assists", 3, "over", "3+ Assists"),
]


@pytest.mark.parametrize("key,thr,direction,text", CASES)
def test_format_market_is_canonical(key, thr, direction, text):
    assert M.format_market(key, thr, direction) == text


@pytest.mark.parametrize("key,thr,direction,text", CASES)
def test_resolve_round_trips(key, thr, direction, text):
    rk, rd = M.resolve(M.MARKETS[key].league, text)
    assert rk == key
    # direction only carries for markets that can be served both ways (SP props)
    if M.MARKETS[key].allows_both:
        assert rd == direction
    else:
        assert rd == "over"


def test_resolve_hits_allowed_before_bare_hit():
    # "hits allowed" contains "hit"; must not misclassify as batter_hit
    assert M.resolve("MLB", "≤ 5 Hits Allowed (SP)")[0] == "sp_hits"
    assert M.resolve("MLB", "1+ Hit")[0] == "batter_hit"


def test_resolve_without_league():
    # league is advisory — phrases are league-unique
    assert M.resolve(None, "7+ Strikeouts (SP)")[0] == "sp_k"
    assert M.resolve(None, "15+ Points")[0] == "wnba_points"
    assert M.resolve(None, "unknown market")[0] is None


def test_grade_directions():
    assert M.grade("sp_k", 7, 7, "over") == "hit"
    assert M.grade("sp_k", 6, 7, "over") == "miss"
    assert M.grade("sp_hits", 4, 5, "under") == "hit"
    assert M.grade("sp_hits", 7, 5, "under") == "miss"
    assert M.grade("batter_hit", 2, 1, "over") == "hit"
    assert M.grade("batter_hit", 0, 1, "over") == "miss"


def test_grade_uses_default_direction_when_omitted():
    # sp_hits defaults to under; batter_hit to over
    assert M.grade("sp_hits", 3, 5, None) == "hit"
    assert M.grade("batter_hit", 1, 1, None) == "hit"


def test_actual_display_units():
    assert M.actual_display("sp_k", 7) == "7 K"
    assert M.actual_display("sp_hits", 5) == "5 hits allowed"
    assert M.actual_display("batter_hit", 1) == "1 hit"
    assert M.actual_display("batter_hit", 2) == "2 hits"
    assert M.actual_display("wnba_points", 22) == "22 pts"
    assert M.actual_display("wnba_rebounds", 4) == "4 reb"
    assert M.actual_display(None, 3) == "3"       # unknown key → bare number


def test_prop_type_taxonomy_backcompat():
    assert M.prop_type("MLB", "1+ Hit") == "hits"
    assert M.prop_type("MLB", "≤ 5 Hits Allowed (SP)") == "sp_hits"
    assert M.prop_type("WNBA", "15+ Points") == "points"
    assert M.prop_type("MLB", "nonsense") == "other"
    assert M.present_types([("MLB", "1+ Hit"), ("MLB", "7+ Strikeouts (SP)"),
                            ("WNBA", "15+ Points")]) == ["hits", "sp_k", "points"]
