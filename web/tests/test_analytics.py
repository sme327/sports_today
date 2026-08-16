from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.http import QueryDict

from web.analytics import apply_filters, parse_results_date, performance_context, results_context


def row(**overrides):
    base = {
        "snapshot_date": "2026-08-14", "league": "MLB", "game_id": "g1",
        "player_id": "1", "player_name": "A Player", "team_name": "Seattle",
        "opponent": "Texas", "market": "1+ Hit", "market_key": "batter_hit",
        "direction": "over", "threshold": 1, "opportunity_score": 90,
        "stability_score": 80, "result": "hit", "actual_value": 1,
        "void_reason": None, "support_evidence": "[]", "risk_evidence": "[]",
        "captured_on": "2026-08-14", "scoring_engine_version": "batter-hit-v5",
    }
    base.update(overrides)
    return base


def test_results_date_never_allows_today_or_future():
    assert parse_results_date("2026-08-20", date(2026, 8, 15)) == date(2026, 8, 14)


def test_filters_combine_market_result_and_score_band():
    rows = [row(), row(player_id="2", result="miss", opportunity_score=82)]
    filtered = apply_filters(rows, {"market": "hits", "result": "hit", "band": "90-94"})
    assert [item["player_id"] for item in filtered] == ["1"]


@patch("web.analytics.grading.load_graded_slate")
def test_results_context_uses_centralized_grades(load):
    load.return_value = [row()]
    context = results_context(QueryDict("date=2026-08-14"), date(2026, 8, 15))
    assert context["prop_count"] == 1
    assert "1–0" in context["summary_html"]
    assert "A Player" in context["prop_html"]


@patch("web.analytics.grading.load_graded_slate")
def test_results_show_the_complete_daily_audit_without_dead_pagination(load):
    load.return_value = [row(player_id=str(index), player_name=f"Player {index}") for index in range(205)]
    context = results_context(QueryDict("date=2026-08-14"), date(2026, 8, 15))
    assert context["prop_count"] == 205
    assert context["visible_start"] == 1 and context["visible_end"] == 205
    assert context["total_pages"] == 1
    assert context["prop_html"].count("prop-item") == 205


@patch("web.analytics.grading.load_graded_range")
def test_performance_context_defaults_to_all_qualifying_predictions(load):
    load.return_value = [row(), row(player_id="2", result="miss", opportunity_score=60)]
    context = performance_context(QueryDict("period=30"), date(2026, 8, 15))
    assert context["has_rows"]
    assert "All qualifying" in context["summary_html"]
    assert "1–0" in context["summary_html"]
    assert context["calibration_read"]


@patch("web.analytics.grading.load_graded_range")
def test_performance_cohort_can_isolate_featured_predictions(load):
    load.return_value = [
        row(featured=True, featured_rank=1),
        row(player_id="2", result="miss", opportunity_score=88,
            featured=False, featured_rank=None),
    ]
    context = performance_context(
        QueryDict("period=30&cohort=featured"), date(2026, 8, 15))
    assert "Featured" in context["summary_html"]
    assert "1–0" in context["summary_html"]
    assert context["cohort"] == "featured"


@patch("web.analytics.grading.load_graded_range")
def test_performance_excludes_total_bases_and_walks(load):
    load.return_value = [
        row(),
        row(player_id="2", market="2+ Total Bases", market_key="batter_tb"),
        row(player_id="3", market="1+ Walks", market_key="batter_bb"),
    ]
    context = performance_context(QueryDict("period=7"), date(2026, 8, 15))
    assert context["has_rows"]
    assert "Total Bases" not in str(context["filter_groups"])
    assert "Walks" not in str(context["filter_groups"])
    assert "1–0" in context["summary_html"]


@patch("web.analytics.grading.load_graded_range")
def test_performance_markets_use_emoji_sport_rows_and_all_links_are_bounded(load):
    load.return_value = [row()]
    context = performance_context(QueryDict("period=7&league=MLB"), date(2026, 8, 15))
    groups = {group["label"]: group for group in context["filter_groups"]}
    assert set(groups) == {"Market", "⚾", "🏀", "Direction"}
    assert [option["label"] for option in groups["Market"]["options"]] == ["All"]
    assert groups["Market"]["options"][0]["active"]
    assert [option["label"] for option in groups["⚾"]["options"]] == [
        "Batter Hits", "Batter Ks", "SP Strikeouts", "SP Hits Allowed",
    ]
    assert [option["label"] for option in groups["🏀"]["options"]] == [
        "Points", "Rebounds", "Assists",
    ]
    market_href = groups["⚾"]["options"][0]["href"]
    assert "market=hits" in market_href and "league=" not in market_href
    assert "result=" not in str(context["filter_groups"])


@patch("web.analytics.grading.load_graded_slate")
def test_results_offer_only_the_seven_published_dates(load):
    load.return_value = [row()]
    context = results_context(QueryDict(""), date(2026, 8, 15))
    assert len(context["recent_dates"]) == 7
    assert context["recent_dates"][0]["date"] == date(2026, 8, 14)
    assert context["recent_dates"][-1]["date"] == date(2026, 8, 8)
    assert context["filter_groups"] == []
