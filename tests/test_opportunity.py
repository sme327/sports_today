

# --- v5: shrinkage weight (2026-08-10) --------------------------------------------

def test_recent_form_is_shrunk_hard_toward_the_league_mean():
    """v5 cut `_HIT_SHRINK` from 0.70 to 0.25 after measuring, on 28,000 leakage-safe
    batter-games, that plate-appearance volume predicts a 1+ hit more than twice as well
    as recent hitting does (+0.1296 vs +0.0539). A hot streak should barely move the
    estimate; how often a batter comes to the plate should move it a lot."""
    from src.opportunity import _HIT_SHRINK, _LEAGUE_HIT_RATE
    assert _HIT_SHRINK <= 0.35, "recent form must stay heavily regressed"
    scorching, league = 0.340, _LEAGUE_HIT_RATE
    shrunk = league + (scorching - league) * _HIT_SHRINK
    # A .340-per-PA tear over 50 PA must not survive as anything like .340.
    assert shrunk < 0.28, f"a hot streak still reaches {shrunk:.3f}"
    assert shrunk > league, "but it must still count for something"


def test_the_lift_scale_holds_the_v5_served_floor():
    """v6 changed what the number *means* (lift over the starting-batter base rate on
    the shared scale), not what this market serves: the estimate needed to reach the
    curation floor must stay where v5 put it (est ≥ .7075), or the served population
    quietly moves under a relabel that claimed to be ordering-neutral."""
    from src import score_scale
    from src.opportunity import _BASE_RATE_1PLUS_HIT, _HIT_SHRINK, _LEAGUE_HIT_RATE

    floor_est = _BASE_RATE_1PLUS_HIT + (70 - 50) / 200.0
    assert abs(floor_est - 0.7075) < 0.005, f"floor now at est {floor_est:.4f}"
    # A league-average batter with typical volume still lands mid-range, not near 0 or 100.
    p = _LEAGUE_HIT_RATE + (0.21 - _LEAGUE_HIT_RATE) * _HIT_SHRINK
    est = 1.0 - (1.0 - p) ** 4.1
    score = score_scale.unified_score(est, _BASE_RATE_1PLUS_HIT)
    assert 20 <= score <= 70, f"average batter scores {score}"


def test_the_batter_base_rate_matches_the_measured_population():
    """The scorer's base-rate constant lives in src (the leaf layer) while the measured
    population lives in services/base_rates. This pins them together so the constant
    cannot drift from the population it claims to describe. Skips when the workbook
    data is absent (base_rates then honestly reports nothing)."""
    import pytest
    from services.base_rates import base_rate
    from src.opportunity import _BASE_RATE_1PLUS_HIT

    measured = base_rate("batter_hit", 1, "over")
    if measured is None:
        pytest.skip("no MLB population loaded")
    assert abs(measured - _BASE_RATE_1PLUS_HIT) < 0.02, (
        f"measured {measured:.3f} vs constant {_BASE_RATE_1PLUS_HIT}")
