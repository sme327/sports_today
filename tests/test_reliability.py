"""Unit tests for the shared reachable-bar selector."""

from __future__ import annotations

import pandas as pd

from src.reliability import highest_reachable_over


def _s(values):
    return pd.Series(values)


def test_picks_highest_bar_that_clears_the_floor():
    # clears 1+ always, 2+ 80%, 3+ 20% → highest reachable at floor .5 is 2.
    vals = _s([2, 2, 1, 3, 2, 2, 1, 2, 3, 2])
    picked = highest_reachable_over(vals, (1, 2, 3), 0.5)
    assert picked is not None
    thr, rate = picked
    assert thr == 2 and rate == 0.8


def test_returns_none_when_no_bar_reaches_floor():
    vals = _s([0, 1, 0, 1, 0, 0, 1, 0, 0, 1])   # 1+ only 40%, nothing at .5
    assert highest_reachable_over(vals, (1, 2, 3), 0.5) is None


def test_floor_is_inclusive():
    vals = _s([1, 1, 0, 0])   # 1+ exactly 50%
    assert highest_reachable_over(vals, (1, 2), 0.5) == (1, 0.5)


def test_empty_series_is_none():
    assert highest_reachable_over(_s([]), (1, 2), 0.5) is None
