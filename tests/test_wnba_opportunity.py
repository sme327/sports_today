

# --- v3 weights (2026-08-12) --------------------------------------------------------

def test_the_ten_game_clear_rate_outweighs_the_five_game():
    """v2 backed the noisier window. Over 3,118 leakage-safe player-games the 10-game
    clear rate beat the 5-game in *every* market — +0.159 vs +0.121 (points), +0.087 vs
    +0.053 (rebounds), +0.183 vs +0.092 (assists). v4 keeps the ratio as a 0.45/0.55
    blend on the shared lift scale."""
    from src.wnba_opportunity import _BASELINE_BLEND, _RECENT_BLEND
    assert _BASELINE_BLEND > _RECENT_BLEND
    assert abs(_RECENT_BLEND + _BASELINE_BLEND - 1.0) < 1e-9


def test_recent_form_no_longer_gets_a_separate_trend_bonus():
    """`clip((avg_l5 - avg_l10) * 2, -5, 8)` correlated +0.031 with clearing the bar — a
    short-window delta on noisy counting stats — while occupying up to 8 points of scale.

    Asserted behaviourally rather than by scanning the source: two players with identical
    clear rates and minutes, differing only in whether their last five *averaged* above
    their last ten, must now score the same."""
    import inspect

    from src import wnba_opportunity
    src = inspect.getsource(wnba_opportunity.score_wnba_opportunities)
    # No live assignment of a trend term (prose mentioning the retired one is fine).
    assert not any(line.strip().startswith("trend_score =") for line in src.splitlines())
    assert "+ trend_score" not in src


def test_base_rate_constants_match_the_measured_population():
    """v4's base-rate table lives in src (the leaf layer) while the measured population
    lives in services/base_rates. This pins them together so the constants cannot drift
    from the populations they claim to describe. Skips without WNBA data loaded."""
    import pytest
    from services.base_rates import base_rate
    from src.wnba_opportunity import _BASE_CLEAR, MARKETS

    checked = 0
    for market, spec in MARKETS.items():
        for threshold in spec["thresholds"]:
            measured = base_rate(f"wnba_{market}", threshold, "over")
            if measured is None:
                continue
            constant = _BASE_CLEAR[market][threshold]
            assert abs(measured - constant) < 0.03, (
                f"wnba_{market} {threshold}+: measured {measured:.3f} vs {constant}")
            checked += 1
    if not checked:
        pytest.skip("no WNBA population loaded")


def test_every_offered_bar_has_a_measured_base_rate():
    """A bar with no base cannot be scored on the lift scale — the scorer skips it rather
    than guessing. So the base table must cover the whole threshold grid, or bars would
    silently vanish from the product."""
    from src.wnba_opportunity import _BASE_CLEAR, MARKETS

    for market, spec in MARKETS.items():
        for threshold in spec["thresholds"]:
            assert threshold in _BASE_CLEAR.get(market, {}), f"{market} {threshold}+"


def test_a_steady_player_outscores_a_streaky_one_on_the_same_bar(monkeypatch):
    """The point of the reweight: someone who clears the bar consistently over ten games
    should rank above someone whose last five happen to look hot."""
    from src.wnba_opportunity import _BASELINE_BLEND, _RECENT_BLEND
    steady_l5, steady_l10 = 0.6, 0.9
    streaky_l5, streaky_l10 = 0.9, 0.6
    steady = _RECENT_BLEND * steady_l5 + _BASELINE_BLEND * steady_l10
    streaky = _RECENT_BLEND * streaky_l5 + _BASELINE_BLEND * streaky_l10
    assert steady > streaky
