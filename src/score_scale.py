"""The shared Opportunity Score scale: estimated lift over the market's own base rate.

**The convention.** ``score = 50 + 200 × (est − base)``, clipped to [0, 100], where
``est`` is the scorer's honest estimate of P(clear) for the exact bar and direction it
is offering, and ``base`` is how often that event happens on its own across the
market's population (the same populations ``services/base_rates`` measures). So:

    50  ⇔ no estimated edge over the base rate
    70  ⇔ estimated +10 points over base   (the curation floor)
    100 ⇔ estimated +25 points over base

**Why one scale.** Before this, every scorer mapped its estimate onto 0–100 with its
own hand-tuned constants, yet one floor (70) and one cross-market ranking were applied
to all of them. The floor therefore meant nothing consistent: ``batter_k``'s scale
topped out at 75 against the floor of 70, so a market with the second-highest measured
lift in the app was served six times in six weeks — found by accident, weeks late.
Serving share per market was an artifact of scale tuning, not a property of the market.

**Evidence (2026-08-20 ledger evaluation; decision log has the full tables).** Across
3,676 graded current-engine props with reconstructable estimates, re-served at matched
volume (n=910), the unified rule's picks realized **+15.0** lift over their own base
rates against **+11.7** for the incumbent per-market scales. The 401 props it newly
served realized +13.0 (including the entire starved ``batter_k`` set); the 58 it
dropped realized +1.9 — the near-worthless high-base easy bars. Top-20% realized lift
improved in six of eight markets. Known cost, stated honestly: full-range correlation
*within* several markets is lower (the old sample-bonus/impressiveness terms carried
some mid-scale ordering) — but no surface serves the mid-scale; the floor, the
featured ranking and the game-page lists all read the top, which is where the
unified scale wins.

**Which engines use it.** ``batter-hit-v6``, ``sp-v4`` (both directions) and
``wnba-pra-v4``. Deliberately *not* migrated: ``batter-k-v2`` (shipped 2026-08-20 with
its own validated weights; migrate once graded), ``batter_bb`` (its clear-rate estimate
is measurably miscalibrated — implied +20 lift against realized −1.3 ±10.6 — and the
market is watch-listed; putting it on this scale would serve a flat market on a number
known to be wrong), and NFL (its five markets shipped with their own measured
base-rate ladders).

**This is still not a probability.** The estimate side is each scorer's own honest
read of a recent window, uncalibrated; the product rule ("Opportunity Score, never
probability") stands. What the scale fixes is comparability: the same number now makes
the same claim in every market.

This module lives in ``src`` (the leaf layer) so scorers can use it; base rates reach
scorers as measured constants beside their thresholds — the pattern ``sp-v3``'s
``_CLEAR_RATES`` established — and a test validates those constants against
``services.base_rates`` so they cannot drift.
"""

from __future__ import annotations

# One point of score per half point of estimated lift.
_POINTS_PER_LIFT = 200.0
_MIDPOINT = 50.0

# Clear-rate estimates from short windows are noisy; shrink toward the base rate by
# sample size before scoring, so three loud games cannot claim a +25 edge. k=3 keeps
# a full 10-game window at ~77% of its own signal.
DEFAULT_SHRINK_GAMES = 3.0


def lift_points(est: float, base: float) -> float:
    """The raw, unclamped score for an estimated clear probability against its base.
    Callers that post-adjust (the lineup overlay's slot nudge) clamp afterwards."""
    return _MIDPOINT + _POINTS_PER_LIFT * (est - base)


def unified_score(est: float, base: float) -> int:
    """The displayed Opportunity Score: 50 = no estimated edge, 70 = +10pp, 100 = +25pp."""
    return max(0, min(round(lift_points(est, base)), 100))


def shrink_toward(base: float, rate: float, n: float,
                  k: float = DEFAULT_SHRINK_GAMES) -> float:
    """Pull a small-sample clear rate toward the base rate: weight n/(n+k)."""
    n = max(float(n), 0.0)
    return base + (rate - base) * n / (n + k)
