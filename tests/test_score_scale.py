"""The shared lift scale: one number, one claim, in every migrated market."""

from src import score_scale


def test_the_convention_anchors():
    """50 = no estimated edge, 70 (the floor) = +10pp over base, 100 = +25pp."""
    assert score_scale.unified_score(0.50, 0.50) == 50
    assert score_scale.unified_score(0.60, 0.50) == 70
    assert score_scale.unified_score(0.75, 0.50) == 100
    # The same lift scores the same regardless of how common the underlying event is —
    # that is the whole point: a rare event cleared often is not penalised for rarity.
    assert score_scale.unified_score(0.20, 0.10) == score_scale.unified_score(0.71, 0.61)


def test_clipping_and_raw_points():
    assert score_scale.unified_score(1.0, 0.0) == 100
    assert score_scale.unified_score(0.0, 1.0) == 0
    # The raw form is unclamped so the lineup overlay can nudge before rounding.
    assert score_scale.lift_points(1.0, 0.0) == 250.0


def test_shrinkage_pulls_small_samples_toward_base():
    """Three loud games cannot claim a +25 edge: the estimate earns its distance from
    the base rate with sample size."""
    base = 0.30
    small = score_scale.shrink_toward(base, 0.90, 3)
    large = score_scale.shrink_toward(base, 0.90, 30)
    assert base < small < large < 0.90
    assert score_scale.shrink_toward(base, 0.90, 0) == base
