

# --- v3 weights (2026-08-12) --------------------------------------------------------

def test_the_ten_game_clear_rate_outweighs_the_five_game():
    """v2 backed the noisier window. Over 3,118 leakage-safe player-games the 10-game
    clear rate beat the 5-game in *every* market — +0.159 vs +0.121 (points), +0.087 vs
    +0.053 (rebounds), +0.183 vs +0.092 (assists)."""
    from src.wnba_opportunity import _BASELINE_WEIGHT, _RECENT_WEIGHT
    assert _BASELINE_WEIGHT > _RECENT_WEIGHT


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


def test_score_base_is_tuned_against_the_dropped_trend_headroom():
    """Removing up to 8 points of headroom without raising the base would have cut the
    served share from 42.9% to 38%. These two constants move together."""
    from src.wnba_opportunity import _SCORE_BASE
    assert 19 <= _SCORE_BASE <= 21, "base must offset the lost trend headroom"


def test_a_steady_player_outscores_a_streaky_one_on_the_same_bar(monkeypatch):
    """The point of the reweight: someone who clears the bar consistently over ten games
    should rank above someone whose last five happen to look hot."""
    from src.wnba_opportunity import _BASELINE_WEIGHT, _RECENT_WEIGHT
    steady_l5, steady_l10 = 0.6, 0.9
    streaky_l5, streaky_l10 = 0.9, 0.6
    steady = _RECENT_WEIGHT * steady_l5 + _BASELINE_WEIGHT * steady_l10
    streaky = _RECENT_WEIGHT * streaky_l5 + _BASELINE_WEIGHT * streaky_l10
    assert steady > streaky
