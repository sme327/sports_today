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

    @property
    def in_game_view(self) -> bool:
        return self.view != "results" and bool(self.game_id and self.league)

    @property
    def in_results_view(self) -> bool:
        return self.view == "results"

    @property
    def in_update_view(self) -> bool:
        return self.view == "update"


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
    if view not in {"today", "results", "update"}:
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
    )
