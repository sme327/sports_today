"""Served vs scored — the headline must measure the advice, not the whole output.

The ledger deliberately records every prop that was scored, but only those clearing
the curation floor are ever shown. Mixing them measures the scorer's entire output
rather than what it recommended, and on real data the two differ by 13.2 points
(46.5% scored against 59.8% served, with 77% of rows never reaching a reader).
"""

from __future__ import annotations

import re

from components.results_feed import period_summary_html
from services import grading


def _row(score, result, league="MLB"):
    return {"opportunity_score": score, "result": result, "league": league}


def test_the_floor_has_one_definition():
    """It was a view constant while Performance needed it too — two copies of a
    number that must agree is how they stop agreeing."""
    import views.today as today
    assert today._CURATION_FLOOR == grading.CURATION_FLOOR


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


def test_headline_leads_with_what_was_recommended():
    rows = [_row(90, "hit")] * 6 + [_row(90, "miss")] * 4 + [_row(20, "miss")] * 50
    overall = grading.tally(rows)
    served = grading.tally(grading.split_served(rows)[0])
    html = period_summary_html(overall, 55.0, "Last 30 days",
                               served=served, floor=grading.CURATION_FLOOR)
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert text.index("60.0%") < text.index("10.0%"), "served must come first"
    assert "shown as picks (70+)" in text
    assert "never cleared the bar" in text          # the population is labelled, not hidden


def test_the_old_single_number_headline_still_works():
    """Callers that pass no served tally keep the previous rendering."""
    html = period_summary_html(grading.tally([_row(90, "hit")]), None, "Season")
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert "100.0%" in text and "shown as picks" not in text


def test_served_rate_beats_the_population_on_real_shape():
    """The whole point: curation should be doing something. If the served subset ever
    converts *worse* than the population, the floor is not selecting for anything."""
    rows = [_row(85, "hit")] * 7 + [_row(85, "miss")] * 3 + [_row(30, "hit")] * 3 + [_row(30, "miss")] * 7
    served = grading.tally(grading.split_served(rows)[0])
    assert served["hit_rate"] > grading.tally(rows)["hit_rate"]
