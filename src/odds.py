"""American odds → probability, for judging a posted line against a player's record.

**Why this exists.** A prop board's whole job is to compare two numbers: how often the
player has cleared the posted number, and how often the price says he will. Doing that
arithmetic in your head across a hundred and fifty lines is unverifiable and it is where a
board quietly goes wrong. These are three lines of maths with a test each.

**What it is not.** The break-even from a single side carries the book's hold, so it
overstates what the market thinks. Where both sides are known, `no_vig` removes it and is
the honest comparison. Nothing here is a model: the market's probability is an input to a
human decision, never a score, and none of it is consumed by the scoring engine.
"""

from __future__ import annotations


def implied_probability(american: float) -> float:
    """The break-even win rate a price demands. −135 → 0.574, +150 → 0.400.

    This is the *priced* probability including the book's margin, which is what a single
    posted side tells you. Use `no_vig` when both sides are known.
    """
    price = float(american)
    if price == 0:
        raise ValueError("American odds cannot be 0; even money is +100 or -100")
    if price < 0:
        return -price / (-price + 100.0)
    return 100.0 / (price + 100.0)


def no_vig(over: float, under: float) -> tuple[float, float]:
    """Both sides' probabilities with the book's hold removed, normalised to 1.

    −115/−115 → (0.500, 0.500); the raw break-evens sum to 1.070, and that 7% is the
    hold, not an opinion about the game.
    """
    a, b = implied_probability(over), implied_probability(under)
    total = a + b
    return a / total, b / total


def hold(over: float, under: float) -> float:
    """The book's margin on a two-way market: 0.070 for a −115/−115 pair."""
    return implied_probability(over) + implied_probability(under) - 1.0


def edge(observed_rate: float, american: float) -> float:
    """Observed clear rate minus the price's break-even, in probability points.

    Positive means the record cleared the number more often than the price demands. This
    is a *descriptive gap on past games*, not an expectation: the sample is small, the
    player's role may have changed, and the market knows things the feed does not. Treat
    it as the first filter, never the answer.
    """
    return float(observed_rate) - implied_probability(american)
