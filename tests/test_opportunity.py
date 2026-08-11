

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


def test_the_score_scale_keeps_the_served_population_stable():
    """Heavier shrinkage compresses the estimate, so the scale has to move with it or the
    curation floor quietly serves half as many props. These two are a matched pair."""
    from src.opportunity import _SCORE_OFFSET, _SCORE_SPAN, _HIT_SHRINK, _LEAGUE_HIT_RATE
    # A league-average batter with typical volume should land mid-range, not near 0 or 100.
    p = _LEAGUE_HIT_RATE + (0.21 - _LEAGUE_HIT_RATE) * _HIT_SHRINK
    est = 1.0 - (1.0 - p) ** 4.1
    score = (est - _SCORE_OFFSET) / _SCORE_SPAN * 100
    assert 20 <= score <= 70, f"average batter scores {score:.0f}"
