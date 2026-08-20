"""How often a prop's event happens on its own — the number a hit rate is judged against.

These tests exist because the comparison they replace was wrong in a way that changed
decisions: every market measured against one blended average, which flatters common events
and punishes rare ones.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from components.results_feed import edge_table_html
from services import base_rates


@pytest.fixture
def db(tmp_path):
    """A tiny league: 2 games, 9 starters a side, plus a bench bat who never starts."""
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE plate_appearances (game_id TEXT, batting_team TEXT,
        pitching_team TEXT, batter_id TEXT, pitcher_id TEXT, inning TEXT, is_hit INT,
        is_strikeout INT, is_walk INT, total_bases INT)""")
    rows = []
    for g in ("g1", "g2"):
        for slot in range(9):
            # Starters 0-3 get a hit; 4-8 do not. Base rate for 1+ hit is therefore 4/9.
            hit = 1 if slot < 4 else 0
            rows.append((g, "TeamA", "TeamB", f"b{slot}", "sp1", "1T", hit, 0, 0, hit))
        # A bench bat with one plate appearance and no hit. He must not count: including
        # him would drag the base rate down and flatter every pick we make.
        rows.append((g, "TeamA", "TeamB", "bench", "sp1", "9T", 0, 0, 0, 0))
    conn.executemany("INSERT INTO plate_appearances VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    base_rates._values.cache_clear()
    base_rates.base_rate.cache_clear()
    return str(path)


def test_the_base_rate_counts_starters_not_everyone_who_batted(db):
    """Nine starters, four with a hit -> 4/9. The bench bat is excluded."""
    assert base_rates.base_rate("batter_hit", 1, "over", db_path=db) == pytest.approx(4 / 9)


def test_an_under_is_inclusive_of_the_bar(db):
    """`markets.grade` resolves an under as `actual <= threshold`. Writing that comparison
    out by hand as `<` once produced a base rate wrong in the flattering direction, which
    turned a losing market into an apparent +12."""
    # Starters allow 0 or 1 total bases each; "under 0" must count the four-of-nine zeros.
    incl = base_rates.base_rate("batter_tb", 0, "under", db_path=db)
    assert incl == pytest.approx(5 / 9), "under 0 must include exactly the players at 0"


def test_no_population_means_no_comparison_rather_than_a_guess(tmp_path):
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    base_rates._values.cache_clear()
    base_rates.base_rate.cache_clear()
    assert base_rates.base_rate("batter_hit", 1, "over", db_path=str(empty)) is None


def test_a_segment_mixing_markets_is_weighted_by_the_props_it_holds(db):
    """Grouping by team or player mixes markets and bars, so the segment's base rate is
    the mean of its own rows' base rates."""
    rows = [{"market_key": "batter_hit", "threshold": 1, "direction": "over"},
            {"market_key": "batter_hit", "threshold": 1, "direction": "over"}]
    assert base_rates.segment_base_rate(rows, db_path=db) == pytest.approx(4 / 9)


# --- the table ----------------------------------------------------------------------

def _tally(hit, miss, rate):
    return {"hit": hit, "miss": miss, "void": 0, "pending": 0, "hit_rate": rate}


def test_the_edge_table_ranks_by_lift_not_by_hit_rate():
    """The defect this column was built to fix: 1+ hit converts higher than WNBA assists
    and is the weaker market, because its event is far more common."""
    seg = {"Batter Hits": _tally(61, 39, 0.614), "WNBA Assists": _tally(66, 34, 0.660)}
    base = {"Batter Hits": 0.607, "WNBA Assists": 0.347}
    html = edge_table_html(seg, 0.62, 10, {}, {}, seg_base=base)
    assert html.index("WNBA Assists") < html.index("Batter Hits")
    assert "+31.3 pp" in html and "+0.7 pp" in html


def test_the_table_shows_the_base_it_compares_against():
    """A lift means nothing without the number it is a lift over."""
    html = edge_table_html({"WNBA Assists": _tally(66, 34, 0.660)}, 0.62, 10, {}, {},
                           seg_base={"WNBA Assists": 0.347})
    assert "base 35%" in html


def test_a_segment_with_no_measurable_base_shows_nothing_not_a_zero():
    html = edge_table_html({"Mystery": _tally(5, 5, 0.5)}, 0.62, 1, {}, {}, seg_base={})
    assert "pp" not in html


def test_the_old_vs_overall_column_is_gone():
    """It compared every market to one blended average and reversed the true ranking."""
    html = edge_table_html({"Batter Hits": _tally(61, 39, 0.614)}, 0.62, 10, {}, {},
                           seg_base={"Batter Hits": 0.607})
    assert "vs overall" not in html
    assert "vs base" in html


def test_calibration_bands_are_measured_against_their_own_mix():
    """The 99-100 band is almost purely 1+ hit; the 70-74 band is half WNBA and SP lines.
    Against one blended average, a band's market mix and its score are indistinguishable."""
    from components.results_feed import calibration_table_html

    bands = {"70–74": _tally(60, 40, 0.60), "99–100": _tally(55, 45, 0.55)}
    html = calibration_table_html(bands, 0.60, {"70–74": 0.53, "99–100": 0.61})
    assert "+7.0 pp" in html and "-6.0 pp" in html
    assert "vs base" in html and "vs overall" not in html


def test_the_calibration_read_follows_lift_not_raw_rate():
    """A top band converting higher can still be the weaker band once its easier mix is
    accounted for — the sentence must not call that an improvement."""
    from components.results_feed import calibration_interpretation

    bands = {"70–74": _tally(60, 40, 0.60), "99–100": _tally(64, 36, 0.64)}
    rising = calibration_interpretation(bands, {"70–74": 0.50, "99–100": 0.45})
    assert "higher" in rising.lower()
    falling = calibration_interpretation(bands, {"70–74": 0.50, "99–100": 0.66})
    assert "not produced higher" in falling


def test_a_month_is_compared_to_its_own_seasonal_mix():
    """League mix is seasonal — a WNBA-heavy month carries rarer events."""
    from components.results_feed import monthly_table_html

    html = monthly_table_html([("2026-07", _tally(64, 36, 0.64))], 0.60,
                              {"2026-07": 0.60})
    assert "+4.0 pp" in html and "base 60%" in html


# --- market pulse column order (2026-08-20) ------------------------------------------

def test_the_pulse_table_reads_summary_first_then_newest_slate():
    """On a phone the columns that matter should be on screen before any scrolling: the
    period aggregate, then the most recent slate, counting back."""
    from components.results_feed import market_trend_matrix_html

    rows = [{"result": "hit", "snapshot_date": d, "league": "MLB",
             "market": "Batter Hits", "market_key": "batter_hit"}
            for d in ("2026-08-16", "2026-08-17", "2026-08-18")]
    rows += [{"result": "miss", "snapshot_date": "2026-08-16", "league": "MLB",
              "market": "Batter Hits", "market_key": "batter_hit"}]
    html = market_trend_matrix_html(rows)
    assert html.index("Period") < html.index("Aug"), "the period summary comes first"
    assert html.index("<b>18</b>") < html.index("<b>16</b>"), "newest slate before oldest"


def test_the_pulse_trend_still_compares_recent_against_prior():
    """Only the display order reverses — the recent-vs-prior arrow depends on the dates
    staying chronological underneath."""
    import inspect

    from components import results_feed

    src = inspect.getsource(results_feed.market_trend_matrix_html)
    assert "shown_dates = list(reversed(dates))" in src
    assert "dates[-3:]" in src and "dates[-6:-3]" in src


# --- performance page, three fixes (2026-08-20) --------------------------------------

def test_the_pulse_compares_lift_when_a_market_s_bar_mix_moves():
    """`batter_hit` has one bar so its base never moves (sd 0.000), but WNBA assists
    ranged from a .07 base to a .55 base across days (sd 0.104). A 40% day was coloured
    identically in both, when one is outstanding and the other poor."""
    from components.results_feed import market_trend_matrix_html

    def rows_for(day, thr, results):
        return [{"result": r, "snapshot_date": day, "league": "WNBA",
                 "market": "Assists", "market_key": "wnba_assists",
                 "threshold": thr, "direction": "over"} for r in results]

    # Same 50% rate both days, but against very different bars.
    rows = rows_for("2026-08-17", 3, ["hit", "miss"]) + rows_for("2026-08-18", 9, ["hit", "miss"])
    bases = {3: 0.60, 9: 0.10}
    plain = market_trend_matrix_html(rows)
    adjusted = market_trend_matrix_html(rows, base_of=lambda r: bases[r["threshold"]])
    assert plain != adjusted, "identical rates against different bars must not look alike"


def test_a_market_with_no_base_falls_back_rather_than_breaking():
    from components.results_feed import market_trend_matrix_html

    rows = [{"result": "hit", "snapshot_date": "2026-08-18", "league": "MLB",
             "market": "Batter Hits", "market_key": "batter_hit"}]
    assert market_trend_matrix_html(rows, base_of=lambda _r: None)


def test_coverage_flags_a_market_that_is_good_but_never_served():
    """`batter_k` carries the second-highest lift of any market and had been served six
    times, because its scorer tops out at 75 against a floor of 70. Every other table on
    the page reads served props, so it looked identical to a market that does not work."""
    from components.results_feed import market_coverage_html

    html = market_coverage_html([
        {"label": "Batter Ks", "recorded_n": 80, "recorded_lift": 0.169,
         "served_n": 4, "served_lift": 0.282},
    ], floor=70)
    # The legend explains the word, so assert the flag itself, not the string.
    assert 'class="mc-flag"' in html
    assert "+16.9 pp" in html


def test_coverage_does_not_flag_a_well_served_market():
    from components.results_feed import market_coverage_html

    html = market_coverage_html([
        {"label": "SP Strikeouts", "recorded_n": 300, "recorded_lift": 0.072,
         "served_n": 225, "served_lift": 0.102},
    ], floor=70)
    assert 'class="mc-flag"' not in html


def test_coverage_does_not_flag_a_market_that_is_simply_bad():
    """Starved and bad look the same on every other table; the flag must separate them."""
    from components.results_feed import market_coverage_html

    html = market_coverage_html([
        {"label": "SP Hits Allowed", "recorded_n": 300, "recorded_lift": -0.04,
         "served_n": 6, "served_lift": -0.036},
    ], floor=70)
    assert 'class="mc-flag"' not in html


def test_calibration_reads_only_the_current_engine():
    """Pooled across versions the 99-100 band showed −6.6 and looked anti-predictive;
    split by engine it is +13.4 for batter-hit-v5 alone. A superseded scorer's
    calibration is not a fact about the one running today."""
    import inspect

    from web import analytics

    src = inspect.getsource(analytics.performance_context)
    assert "MODEL_VERSIONS" in src and "current_rows" in src
    assert "calibration_scope" in src


# --- batter-k-v2: the opposing starter (2026-08-20) -----------------------------------

def _k_frame(per_game_ks, team="Team A", pitcher_ks=None, batter="101"):
    """Plate appearances for one batter, plus an opposing starter's own history."""
    rows = []
    for i, k in enumerate(per_game_ks):
        for j in range(4):
            rows.append({"batting_team": team, "batter_id": batter, "batter_name": batter,
                         "game_date": f"2026-06-{i + 1:02d}", "game_id": f"g{i}",
                         "pitcher_id": "other", "is_walk": 0,
                         "is_strikeout": 1 if j < k else 0})
    # A league of starters, so the 10th/90th percentile band the term normalises against
    # is not degenerate. With a single pitcher there is no league context and the term
    # correctly falls back to neutral — which would make this test vacuous.
    for name, rate in (("SP1", pitcher_ks or 0), ("SPlow", 2), ("SPmid", 6), ("SPhigh", 11)):
        for i in range(8):
            for j in range(30):
                rows.append({"batting_team": "Other", "batter_id": str(900 + j),
                             "batter_name": "x", "game_date": f"2026-06-{i + 1:02d}",
                             "game_id": f"p{name}{i}", "pitcher_id": name, "is_walk": 0,
                             "is_strikeout": 1 if j < rate else 0})
    return pd.DataFrame(rows)


def test_the_opposing_starter_moves_a_strikeout_prop():
    """After the reachable-bar filter the batter's own clear rate is noise (AUC 0.515);
    the opposing starter is not (0.566). It is the term that carries this market."""
    from src.batter_kbb_opportunity import score_k_opportunities

    pa = _k_frame([2] * 12, pitcher_ks=14)          # SP1 fans far more than the league
    hot = score_k_opportunities(pa, ["Team A"], opposing_starters={"Team A": "SP1"})
    cold = score_k_opportunities(pa, ["Team A"], opposing_starters={})
    assert not hot.empty and not cold.empty
    assert hot.iloc[0]["opportunity_score"] != cold.iloc[0]["opportunity_score"]


def test_an_unposted_starter_is_named_and_costs_confidence():
    """Scored neutrally — we cannot rank it down on merit we never measured — so the doubt
    lands on stability. Otherwise the top prop on a slate is the one we know least about."""
    from src.batter_kbb_opportunity import (_UNKNOWN_SP_STABILITY_CAP,
                                            score_k_opportunities)

    pa = _k_frame([2] * 12)
    scored = score_k_opportunities(pa, ["Team A"], opposing_starters={})
    assert not scored.empty
    row = scored.iloc[0]
    assert any("not posted" in r for r in row["risks"])
    assert row["stability_score"] <= _UNKNOWN_SP_STABILITY_CAP


def test_impressiveness_is_measured_rarity_not_the_bar_number():
    """`threshold / max(thresholds)` was a constant in practice — the 3+ bar is never
    reachable, so 100% of picks are the 2+ bar — and it capped the scale at 75."""
    from src.batter_kbb_opportunity import _K_BASE

    assert _K_BASE[2] > _K_BASE[3], "2+ K must be the commoner event"
    assert 0.15 < _K_BASE[2] < 0.30
