from __future__ import annotations

import os
from datetime import date, datetime
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")

import django

django.setup()

from django.test import Client, SimpleTestCase
from domain.models import DataStatus, SourceStatus
from web.today import parse_day, parse_threshold


class NavigationParsingTests(SimpleTestCase):
    def test_invalid_day_defaults_to_today(self):
        assert parse_day("later", date(2026, 8, 15)) == ("today", date(2026, 8, 15))

    def test_tomorrow_advances_one_day(self):
        assert parse_day("tomorrow", date(2026, 8, 15)) == ("tomorrow", date(2026, 8, 16))

    def test_threshold_is_restricted_to_supported_values(self):
        assert parse_threshold("85") == 85
        assert parse_threshold("100") == 90
        assert parse_threshold("bad") == 90


class EndpointTests(SimpleTestCase):
    def test_health(self):
        response = Client().get("/health/")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @patch("web.views.results_context", return_value={"section": "results", "has_rows": False})
    def test_results_endpoint(self, _context):
        response = Client().get("/results/")
        assert response.status_code == 200
        assert b"Daily Results" in response.content
        assert b"favicons/results.svg" in response.content

    @patch("web.views.performance_context", return_value={
        "section": "performance", "has_rows": False, "period_options": [],
        "sample_options": [], "filter_groups": [],
    })
    def test_performance_endpoint(self, _context):
        response = Client().get("/performance/")
        assert response.status_code == 200
        assert b"Performance" in response.content
        assert b"favicons/performance.svg" in response.content

    @patch("web.views.build_context")
    def test_today_renders_public_page(self, build_context):
        build_context.return_value = {
            "day": "today",
            "slate_date": date(2026, 8, 15),
            "collapsed": False,
            "threshold": 90,
            "league_filters": [{"key": "MLB", "label": "⚾ MLB", "active": False}],
            "schedule_groups": [],
            "game_count": 2,
            "unjudged": "",
            "errors": [],
            "has_analysis": False,
            "focus_label": None,
            "chosen_prop": None,
            "prop_filters": [],
            "opportunity_summary": "",
            "opportunity_html": "",
            "has_scored_opportunities": False,
            "freshness": type("Fresh", (), {"mlb_through": None, "wnba_through": None})(),
            "feed_calculated_at": None,
            "timing": {"schedule_ms": 1, "feed_ms": 2, "total_ms": 3},
            "current_leagues": [],
        }
        response = Client().get("/")
        assert response.status_code == 200
        assert b"Sports" in response.content
        assert b"favicons/sports-today.svg" in response.content
        # One segmented state control, not two independent booleans on the same axis.
        assert b"data-state-filter" in response.content
        for state in (b"All", b"Live", b"Upcoming", b"Final"):
            assert state in response.content
        assert b"The games and player performances worth your attention" not in response.content
        assert "app;dur=3" in response["Server-Timing"]
        build_context.assert_called_once()

    @patch("web.views.build_context")
    @patch("web.views.refresh_schedules")
    @patch("web.views.load_cached_schedules")
    def test_schedule_refresh_is_deferred_to_fragment(
        self, load_cached, refresh_schedules, build_context
    ):
        load_cached.return_value = {
            "MLB": ([], DataStatus("MLB", SourceStatus.EMPTY, datetime(2026, 8, 15, 1)))
        }
        build_context.return_value = {
            "schedule_groups": [], "errors": [], "game_count": 0, "unjudged": ""
        }
        response = Client().get("/fragments/schedule/?day=today")
        assert response.status_code == 200
        refresh_schedules.assert_called_once()


class SimpleGamePageTests(SimpleTestCase):
    """The matchup page for a league that arrives as a schedule and nothing else."""

    def _game(self, away_record="2-0", home_record="1-1"):
        from datetime import datetime

        from domain.models import SlateGame

        return SlateGame(league="NCAAF", game_id="401", status="scheduled",
                         start_time=datetime(2026, 9, 5, 19, 30),
                         away_name="Georgia Bulldogs", home_name="Alabama Crimson Tide",
                         away_record=away_record, home_record=home_record)

    def test_it_states_what_it_cannot_show(self):
        """These leagues have no feed. Saying so beats implying a richer page exists."""
        from datetime import date

        from web.simple_game import simple_game_context

        ctx = simple_game_context(self._game(), date(2026, 9, 5), "today")
        assert "schedule only" in ctx["gaps"]
        assert "no player props" in ctx["gaps"]

    def test_an_early_season_record_earns_no_read(self):
        """College football starts before its records mean anything — a 2-0 team may have
        played nobody. `Standing.win_pct` is None below four games, so the read says so
        rather than calling a 2-0 team elite."""
        from datetime import date

        from web.simple_game import simple_game_context

        ctx = simple_game_context(self._game(), date(2026, 9, 5), "today")
        assert "2-0 on noise" in ctx["editorial_html"]

    def test_the_migration_stub_is_gone(self):
        """It told readers the page "has not moved to Django yet" — scaffolding that
        outlived the migration and would have greeted every September reader."""
        from pathlib import Path

        assert not (Path("web/templates/web") / "game_pending.html").exists()

    def test_schedule_only_leagues_now_offer_the_link(self):
        from leagues.ncaaf.adapter import NCAAFAdapter

        assert NCAAFAdapter().supports_deep_dive is True
