

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
