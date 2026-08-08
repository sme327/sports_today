"""Shared reachable-bar threshold selection.

Several scorers — total bases, WNBA points/rebounds/assists, batter strikeouts and
walks — converged on the same rule after the graded ledger showed that "impressive
but rarely reached" bars don't convert (TB 4+ hit 20%, SP overs regressed, WNBA
below-50%-clear picks hit 18–44%): offer a prop only on a threshold the player
actually clears often. This is that one decision, factored out so the four scorers
share it. (SP's two-directional over/under choice is a different rule and stays in
`pitcher_opportunity`.)
"""

from __future__ import annotations

import pandas as pd


def highest_reachable_over(values: pd.Series, thresholds, min_clear: float):
    """The highest threshold cleared (``values >= t``) in at least ``min_clear`` of the
    games, paired with its clear-rate — or ``None`` when none qualifies (no reachable
    bar, so the market should skip this player).

    ``values`` is a per-game stat series. Callers keep their own impressiveness and
    return shape; only the reliability decision lives here."""
    if values is None or len(values) == 0:
        return None
    reachable = [(t, float((values >= t).mean())) for t in thresholds]
    reachable = [(t, rate) for t, rate in reachable if rate >= min_clear]
    return max(reachable, key=lambda tr: tr[0]) if reachable else None
