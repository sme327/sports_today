"""Query-parameter navigation state and top-level view dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import streamlit as st


@dataclass(frozen=True)
class NavState:
    day: str            # "today" | "tomorrow"
    slate_date: date
    league: str | None
    game_id: str | None
    games_collapsed: bool = False   # Today page: schedule grid collapsed (?games=off)
    view: str = "today"             # "today" | "results"
    results_date: date | None = None  # the graded slate being viewed (view == "results")
    focus_game: str | None = None   # Today page: filter props to one game (?focus=<id>)
    prop_threshold: int = 90        # global "strong pick" bar for card counts (?thr=)

    @property
    def in_game_view(self) -> bool:
        return self.view != "results" and bool(self.game_id and self.league)

    @property
    def in_results_view(self) -> bool:
        return self.view == "results"

    @property
    def in_update_view(self) -> bool:
        return self.view == "update"

    @property
    def in_performance_view(self) -> bool:
        return self.view == "performance"

    @property
    def in_nfl_view(self) -> bool:
        return self.view == "nfl"


def _parse_results_date() -> date:
    """The graded slate to show (default yesterday). Never today/future — results
    aren't in yet — so it is clamped to at most yesterday."""
    yesterday = date.today() - timedelta(days=1)
    raw = st.query_params.get("date")
    if raw:
        try:
            return min(date.fromisoformat(raw), yesterday)
        except ValueError:
            pass
    return yesterday


def read_nav() -> NavState:
    day = st.query_params.get("day", "today")
    if day not in {"today", "tomorrow"}:
        day = "today"
    slate = date.today() + (timedelta(days=1) if day == "tomorrow" else timedelta(0))
    view = st.query_params.get("view", "today")
    if view not in {"today", "results", "update", "performance", "nfl"}:
        view = "today"
    return NavState(
        day=day,
        slate_date=slate,
        league=st.query_params.get("league"),
        game_id=st.query_params.get("game"),
        games_collapsed=st.query_params.get("games") == "off",
        view=view,
        results_date=_parse_results_date() if view == "results" else None,
        focus_game=st.query_params.get("focus"),
        prop_threshold=_parse_threshold(),
    )


def _parse_threshold() -> int:
    raw = st.query_params.get("thr")
    try:
        return int(raw) if raw and int(raw) in (85, 90, 95) else 90
    except ValueError:
        return 90
