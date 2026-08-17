from components.results_feed import market_trend_matrix_html


def _row(day, market, key, result, league="MLB"):
    return {
        "snapshot_date": day,
        "league": league,
        "market": market,
        "market_key": key,
        "result": result,
    }


def test_market_pulse_combines_markets_and_recent_slates():
    rows = [
        _row("2026-08-10", "1+ Hit", "batter_hit", "hit"),
        _row("2026-08-11", "1+ Hit", "batter_hit", "miss"),
        _row("2026-08-11", "5+ Strikeouts", "sp_k", "hit"),
        _row("2026-08-12", "15+ Points", "wnba_points", "hit", "WNBA"),
    ]
    html = market_trend_matrix_html(rows)
    assert "Batter Hits" in html and "SP Strikeouts" in html and "Points" in html
    assert "Aug<b>10</b>" in html and "Aug<b>12</b>" in html
    assert "Market hit rates by recent slate" in html
    assert "Above own average" in html and "Below own average" in html


def test_market_pulse_excludes_pending_and_marks_small_cells():
    rows = [
        _row("2026-08-10", "1+ Hit", "batter_hit", "hit"),
        _row("2026-08-11", "1+ Hit", "batter_hit", "pending"),
    ]
    html = market_trend_matrix_html(rows)
    assert "small" in html
    assert "Aug<b>11</b>" not in html
