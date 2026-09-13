"""American odds arithmetic: the break-even a price demands, and the hold removed."""

from __future__ import annotations

import pytest

from src.odds import edge, hold, implied_probability, no_vig


@pytest.mark.parametrize("price, expected", [
    (-110, 0.5238), (-115, 0.5349), (-135, 0.5745), (-250, 0.7143),
    (100, 0.5000), (-100, 0.5000), (110, 0.4762), (150, 0.4000), (185, 0.3509),
])
def test_break_even_for_a_posted_price(price, expected):
    assert implied_probability(price) == pytest.approx(expected, abs=5e-5)


def test_zero_is_refused_because_even_money_is_plus_or_minus_100():
    with pytest.raises(ValueError):
        implied_probability(0)


def test_the_hold_is_removed_and_the_two_sides_sum_to_one():
    over, under = no_vig(-115, -115)
    assert over == pytest.approx(0.5) and under == pytest.approx(0.5)
    assert hold(-115, -115) == pytest.approx(0.0698, abs=5e-4)

    # A real pair from the 2026-09-13 boards: Coleman 1.5 receptions, +155 / -210.
    over, under = no_vig(155, -210)
    assert over + under == pytest.approx(1.0)
    assert over == pytest.approx(0.366, abs=1e-3)
    # The raw break-even overstates the under; removing the hold moves it down.
    assert under < implied_probability(-210)


def test_edge_is_the_gap_between_the_record_and_the_price():
    # Keon Coleman cleared 1.5 receptions in 12 of 13 (92%) at +155 (break-even 39%).
    assert edge(12 / 13, 155) == pytest.approx(0.5316, abs=1e-3)
    # A line priced exactly at the observed rate has no gap.
    assert edge(implied_probability(-135), -135) == pytest.approx(0.0)
    # A record worse than the price demands is negative.
    assert edge(0.40, -150) < 0
