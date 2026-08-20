

# --- the raw recent line (2026-08-12) ----------------------------------------------

def _op(**kw):
    from domain.models import Opportunity
    base = dict(league="MLB", player_id="1", player_name="A Player", team_id="1",
                team_name="Cleveland", market="1+ Hit", threshold=1,
                opportunity_score=90, stability_score=88,
                supporting_evidence=["Batting 1st"], negative_evidence=[])
    base.update(kw)
    return Opportunity(**base)


def test_the_raw_line_is_rendered_with_cleared_games_marked():
    """A score compresses ten games into one number and hides the shape. Three players
    can all score 100 on 10/10, 9/10 and 9/10 with very different distributions — the
    line is the fact under our judgement, and what lets a reader disagree with us."""
    from components.opportunity_feed import opportunity_feed_html
    html = opportunity_feed_html([_op(recent_line=[1, 2, 3, 0, 1], line_threshold=1)])
    assert "op-line" in html
    assert html.count('class="op-lv hit"') == 4      # every game except the 0
    assert "4/5" in html


def test_an_under_marks_the_games_at_or_below_the_bar():
    """Testing `>=` on an under would mark exactly the wrong games — a pitcher's best
    starts would render as failures."""
    from components.opportunity_feed import opportunity_feed_html
    html = opportunity_feed_html([_op(market="5 or fewer Hits Allowed", direction="under",
                                      threshold=5, recent_line=[3, 4, 7, 2, 5],
                                      line_threshold=5)])
    assert html.count('class="op-lv hit"') == 4      # 3, 4, 2, 5 cleared; 7 did not
    assert "4/5" in html


def test_a_prop_with_no_line_renders_nothing_extra():
    """Scorers that do not supply a line must not leave an empty strip behind."""
    from components.opportunity_feed import opportunity_feed_html
    assert "op-line" not in opportunity_feed_html([_op()])


def test_the_line_survives_values_that_are_not_whole_numbers():
    from components.opportunity_feed import opportunity_feed_html
    html = opportunity_feed_html([_op(recent_line=[1.5, 2.0], line_threshold=1)])
    assert "1.5" in html and ">2<" in html            # 2.0 renders as "2", not "2.0"


# --- the picks shortlist affordance (2026-08-20) -----------------------------------

def test_rows_carry_the_pick_affordance_and_its_data():
    """The shortlist script stores exactly what the row declares — it never parses
    rendered text, so every stored field must ship as a data attribute."""
    from components.opportunity_feed import opportunity_feed_html
    html = opportunity_feed_html([_op(market_key="batter_hit")])
    assert 'class="op-pick"' in html and 'aria-pressed="false"' in html
    assert 'data-pick-league="MLB"' in html
    assert 'data-pick-player-id="1"' in html
    assert 'data-pick-player="A Player"' in html
    assert 'data-pick-market-key="batter_hit"' in html
    assert 'data-pick-market="1+ Hit"' in html
    assert 'data-pick-threshold="1"' in html
    assert 'data-pick-score="90"' in html
    assert 'data-pick-team="Cleveland"' in html


def test_a_missing_market_key_falls_back_to_the_market_label():
    """Legacy scorers never set market_key. The Results join uses the same fallback
    (stored market text), so both sides derive identical keys."""
    from components.opportunity_feed import opportunity_feed_html
    html = opportunity_feed_html([_op(market_key=None)])
    assert 'data-pick-market-key="1+ Hit"' in html
