"""Offline tests for the R2 Daily Results components (pure HTML)."""

from __future__ import annotations

import json

from components import results_feed as F


def _tally(hit, miss, void=0, pending=0):
    dec = hit + miss
    return {"hit": hit, "miss": miss, "void": void, "pending": pending,
            "total": hit + miss + void + pending, "hit_rate": (hit / dec) if dec else None}


def test_daily_scorecard_ranks_the_three_metrics_above_the_counts():
    """Record, hit rate and average score are the answer to "how did we do"; graded,
    void and pending are the answer to "on how much". Six equal tiles asked the reader
    to weigh a void count against a hit rate."""
    html = F.daily_summary_html(_tally(79, 71, void=26, pending=5), 88.4, 181)
    assert "79–71" in html and "52.7%" in html and "88" in html
    primary = html.split('<div class="ds-secondary">')[0]
    assert primary.count("ds-tile") == 3
    for label, value in (("Graded", "150"), ("Void", "26"), ("Pending", "5")):
        assert label in html and value in html
    assert "ds-info" in html, "the score carries its own 'not a probability' note"
    # nothing decided → "Not graded", never a bare 0%
    assert "Not graded" in F.daily_summary_html(_tally(0, 0, void=3), None, 3)


def test_the_comparison_line_shows_the_lift_beside_the_hit_rate():
    """A day heavy in easy bars beats the 30-day average with nothing having gone right,
    so the raw delta never appears alone — the lift over base is the honest half."""
    html = F.hit_rate_context_html({
        "day_rate": .707, "day_decided": 82, "prior_rate": .625, "prior_decided": 2800,
        "day_lift": .134, "prior_lift": .105, "days": 30})
    assert "70.7%" in html and "+8.2 pts" in html and "hrc-up" in html
    assert "+13.4 pts over base" in html and "+10.5 pts" in html


def test_a_difference_too_small_to_act_on_is_not_coloured():
    html = F.hit_rate_context_html({
        "day_rate": .625, "day_decided": 80, "prior_rate": .618, "prior_decided": 2800,
        "day_lift": .09, "prior_lift": .10, "days": 30})
    assert "roughly in line with the 30-day average" in html
    assert "hrc-up" not in html and "hrc-down" not in html


def test_no_trailing_sample_means_no_comparison_rather_than_a_bare_number():
    html = F.hit_rate_context_html({"day_rate": .70, "day_decided": 20,
                                    "prior_rate": .6, "prior_decided": 4}, min_prior=30)
    assert html == "" or "30-day average" not in html


def _read(**over):
    base = {"day_rate": .707, "day_decided": 82, "day_lift": .134, "prior_lift": .105,
            "day_base": .57, "prior_base": .52, "days": 30, "top_n": 10, "top_missed": 2,
            "top_hit": 8, "top_rate": .8, "min_day": 20, "min_market": 5, "read_market": 10,
            "markets": []}
    base.update(over)
    return base


def test_the_daily_read_judges_the_day_on_lift_not_on_the_hit_rate():
    """A slate of low bars beats the average without anything having gone right, so the
    verdict is read off the base rate and an easier-than-usual mix is named."""
    html = F.daily_read_html(_read(day_base=.60, prior_base=.52))
    assert "A strong day" in html and "+13.4 pts" in html
    assert "bars were lower than usual" in html and "flatters" in html
    # No edge is not "ordinary": at zero lift the picking did nothing.
    assert "No edge today" in F.daily_read_html(_read(day_lift=-.014, prior_lift=.10))


def test_the_daily_read_stays_quiet_when_nothing_is_worth_saying():
    """Three bullets every day is three bullets nobody reads."""
    quiet = F.daily_read_html(_read(day_base=.53, prior_base=.52, top_missed=3,
                                    top_hit=7, top_rate=.7))
    assert quiet.count("<li>") == 1, quiet
    assert "bars were" not in quiet          # a 1-point mix gap says nothing
    assert "top of the scale" not in quiet   # 7–3 at a .707 day is the expectation


def test_a_short_slate_is_reported_as_unreadable_rather_than_judged():
    html = F.daily_read_html(_read(day_decided=6))
    assert "A short slate" in html and "not a verdict" in html
    assert "strong day" not in html


def test_the_read_names_a_market_only_on_a_sample_worth_naming_one_on():
    markets = [
        {"label": "Batter Hits", "hit": 43, "miss": 18, "decided": 61, "lift": .099,
         "hit_rate": .705},
        {"label": "SP Hits Allowed", "hit": 6, "miss": 2, "decided": 8, "lift": .271,
         "hit_rate": .75},
    ]
    html = F.daily_read_html(_read(markets=markets))
    assert "SP Hits Allowed" not in html, "8 decided props is a table row, not a story"
    assert "Batter Hits" not in html, "with one eligible market there is nothing to rank"


def test_a_winning_record_can_still_be_the_weak_spot():
    """43–18 looks like a good day; if those props land 75% of the time unprompted it
    was not one. This is the comparison the project treats a shared average as a bug for."""
    markets = [
        {"label": "SP Strikeouts", "hit": 9, "miss": 4, "decided": 13, "lift": .213,
         "hit_rate": .692},
        {"label": "Batter Hits", "hit": 43, "miss": 18, "decided": 61, "lift": -.06,
         "hit_rate": .705},
    ]
    html = F.daily_read_html(_read(markets=markets))
    assert "was the weak spot" in html and "land more often than that unprompted" in html


def test_the_market_table_reports_lift_only_where_the_sample_supports_it():
    rows = [
        {"label": "Batter Hits", "hit": 43, "miss": 18, "void": 2, "pending": 0,
         "decided": 61, "lift": .099, "avg_score": 74.2, "hit_rate_display": "70.5%"},
        {"label": "Rebounds", "hit": 2, "miss": 1, "void": 0, "pending": 0,
         "decided": 3, "lift": .40, "avg_score": 81.0, "hit_rate_display": "66.7%"},
    ]
    html = F.market_table_html(rows, min_lift_sample=5)
    assert "+9.9 pts" in html and "mkt-lift up" in html
    assert "+40.0 pts" not in html, "three decided props cannot carry a lift claim"
    assert "2 void" in html and "74" in html


def test_confident_misses_are_the_highest_scored_ones_not_the_widest_gaps():
    misses = [{"opportunity_score": 98, "player_name": "Nick Lodolo",
               "market_label": "SP Strikeouts", "recommendation": "Under 5.5",
               "actual": "6 K"}]
    html = F.confident_misses_html(misses, 10, 2)
    assert "Highest-scored misses" in html and "Nick Lodolo" in html
    assert "2 misses among the day's 10 strongest predictions" in html
    assert F.confident_misses_html([], 10, 0) == ""


def test_prop_item_disambiguates_recommendation_and_actual():
    r = {"league": "MLB", "player_name": "Freddie Freeman", "team_name": "Los Angeles Dodgers",
         "opponent": "Padres", "market": "1+ Hit", "market_key": "batter_hit",
         "direction": "over", "threshold": 1, "opportunity_score": 100, "result": "hit",
         "actual_value": 1.0, "support_evidence": json.dumps(["Reaching base often"]),
         "risk_evidence": json.dumps(["Small sample"])}
    html = F.prop_list_html([r])
    assert "Over 0.5" in html and "1 hit" in html          # prediction, then outcome
    assert "HIT" in html and "prop-grade r-hit" in html
    assert "Why this score?" in html and "Reaching base often" in html
    assert "<details" in html
    # The aria label still reads as a sentence: five adjacent spans otherwise run
    # together as "HITFreddie FreemanLos Angeles Dodgers vs Padres".
    assert "Batter Hits, Over 0.5. Score 100. Actual: 1 hit" in html
    # Aligned columns need a heading row to align to.
    assert "prop-head" in html and ">Prediction<" in html


def test_prop_rows_carry_what_the_filter_and_sort_controls_read():
    """The published site is static — a filter cannot be a link, so the controls
    re-arrange the rendered rows and read these attributes rather than the text."""
    r = {"league": "MLB", "player_id": "1", "player_name": "Zack Wheeler",
         "team_name": "Philadelphia Phillies", "opponent": "Mets", "market": "6+ Strikeouts",
         "market_key": "sp_k", "direction": "over", "threshold": 6,
         "opportunity_score": 93, "result": "miss", "actual_value": 4.0}
    html = F.prop_list_html([r])
    assert 'data-market="sp_k"' in html and 'data-market-label="SP Strikeouts"' in html
    assert 'data-score="93"' in html and 'data-order="0"' in html
    assert 'data-player="Zack Wheeler"' in html and 'data-result="miss"' in html


def test_prop_item_carries_shortlist_join_keys():
    """The device-local shortlist joins client-side on league|player_id|market_key.
    The fallback when market_key is absent is the stored market text — the same
    fallback the feed side uses, so both sides derive identical keys."""
    r = {"league": "MLB", "player_id": "660271", "player_name": "X", "team_name": "T",
         "opponent": "O", "market": "1+ Hit", "market_key": "batter_hit",
         "direction": "over", "threshold": 1, "opportunity_score": 90, "result": "hit"}
    html = F.prop_list_html([r])
    assert 'data-league="MLB"' in html and 'data-player-id="660271"' in html
    assert 'data-market-key="batter_hit"' in html and 'data-result="hit"' in html
    legacy = F.prop_list_html([{**r, "market_key": None}])
    assert 'data-market-key="1+ Hit"' in legacy


def test_prop_void_shows_reason():
    r = {"league": "MLB", "player_name": "X", "team_name": "T", "opponent": "O",
         "market": "1+ Hit", "market_key": "batter_hit", "direction": "over", "threshold": 1,
         "opportunity_score": 90, "result": "void", "void_reason": "did not bat"}
    html = F.prop_list_html([r])
    assert "VOID" in html and "did not bat" in html


def _fr(league="MLB", market="1+ Hit", key="batter_hit", score=90, direction="over", result="hit"):
    return {"league": league, "market": market, "market_key": key,
            "opportunity_score": score, "direction": direction, "result": result}


def test_apply_filters_each_dimension_and_combined():
    """Re-pointed at `web.analytics` when the Streamlit filter bar retired. The live
    implementation uses full key names (`league`/`market`/`direction`) where the old one
    used query-param abbreviations (`flg`/`mkt`/`dir`) — a separate implementation, not a
    rename, which is why the assertions are restated rather than moved."""
    from web.analytics import apply_filters
    rows = [
        _fr(result="hit", score=97),
        _fr(result="miss", score=82),
        _fr(league="WNBA", market="15+ Points", key="wnba_points", result="hit", score=91),
        _fr(market="5 or fewer Hits Allowed", key="sp_hits", direction="under",
            result="void", score=88),
    ]
    A = apply_filters
    assert len(A(rows, {"league": "MLB"})) == 3
    assert len(A(rows, {"result": "hit"})) == 2
    assert len(A(rows, {"direction": "under"})) == 1
    assert len(A(rows, {"league": "MLB", "result": "hit"})) == 1   # combined
    assert len(A(rows, {})) == 4                        # empty = no-op
