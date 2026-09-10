"""Qualifying vs research-only and the explicitly named Performance cohort."""

from __future__ import annotations

import re

from components.results_feed import performance_summary_html
from services import grading


def _row(score, result, league="MLB"):
    return {"opportunity_score": score, "result": result, "league": league}


def test_the_floor_has_one_definition():
    """It was a view constant while Performance needed it too — two copies of a number
    that must agree is how they stop agreeing. Re-pointed at the web layer when the
    Streamlit views retired; the invariant is what matters, not which surface holds it."""
    import inspect

    from web import today as web_today
    src = inspect.getsource(web_today)
    assert "grading.CURATION_FLOOR" in src, (
        "web/today.py must read the shared floor, not redeclare its own copy")
    assert not re.search(r"^_CURATION_FLOOR\s*=", src, re.M), (
        "a second definition of the curation floor has appeared")


def test_split_uses_the_floor_inclusively():
    rows = [_row(69, "hit"), _row(70, "hit"), _row(71, "miss")]
    served, below = grading.split_served(rows)
    assert [r["opportunity_score"] for r in served] == [70, 71]
    assert [r["opportunity_score"] for r in below] == [69]


def test_a_missing_score_counts_as_below_the_floor():
    """Never shown, so never counted as advice."""
    served, below = grading.split_served([{"result": "hit"}, {"opportunity_score": None, "result": "miss"}])
    assert served == [] and len(below) == 2


def test_the_two_populations_are_disjoint_and_complete():
    rows = [_row(s, "hit") for s in (10, 50, 69, 70, 95)]
    served, below = grading.split_served(rows)
    assert len(served) + len(below) == len(rows)
    assert not ({id(r) for r in served} & {id(r) for r in below})


def test_headline_names_the_evaluated_cohort_and_independent_slates():
    """A hit rate with no named population is not a claim anyone can check. The headline
    has to say *which* predictions it counted and over how many independent slates —
    prediction counts are correlated within a slate, so 2,723 props over 27 days is far
    less independent evidence than 2,723 draws."""
    rows = [_row(90, "hit")] * 6 + [_row(90, "miss")] * 4 + [_row(20, "miss")] * 50
    qualifying = grading.tally(grading.split_served(rows)[0])
    html = performance_summary_html(
        qualifying, 0.11, grading.tally([]), None, "previous 30 days",
        avg_score=90.0, slates=4, period_label="Last 30 days", cohort="All qualifying",
        base_rate=0.49)
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert "60.0%" in text
    assert "All qualifying" in text
    assert "4 slates" in text


def test_the_headline_shows_lift_over_baseline_beside_the_raw_rate():
    """The reason the old headline was replaced. 60% reads as skill; +11 points over a
    49% base rate is the claim the page is actually entitled to make, and the two must
    carry equal weight rather than one being a footnote to the other."""
    qualifying = grading.tally([_row(90, "hit")] * 6 + [_row(90, "miss")] * 4)
    html = performance_summary_html(
        qualifying, 0.11, grading.tally([]), None, "previous 30 days",
        period_label="Season", cohort="All qualifying", base_rate=0.49)
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert "60.0%" in text and "+11.0 pts" in text and "vs 49% base" in text


def test_a_headline_with_no_measurable_base_says_so_rather_than_showing_a_zero():
    qualifying = grading.tally([_row(90, "hit")])
    html = performance_summary_html(
        qualifying, None, grading.tally([]), None, "previous 30 days",
        period_label="Season", cohort="All qualifying", base_rate=None)
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert "no base measured" in text
    assert "+0.0 pts" not in text


def test_served_rate_beats_the_population_on_real_shape():
    """The whole point: curation should be doing something. If the served subset ever
    converts *worse* than the population, the floor is not selecting for anything."""
    rows = [_row(85, "hit")] * 7 + [_row(85, "miss")] * 3 + [_row(30, "hit")] * 3 + [_row(30, "miss")] * 7
    served = grading.tally(grading.split_served(rows)[0])
    assert served["hit_rate"] > grading.tally(rows)["hit_rate"]
