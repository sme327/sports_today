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

    @property
    def in_game_view(self) -> bool:
        return bool(self.game_id and self.league)


def read_nav() -> NavState:
    day = st.query_params.get("day", "today")
    if day not in {"today", "tomorrow"}:
        day = "today"
    slate = date.today() + (timedelta(days=1) if day == "tomorrow" else timedelta(0))
    return NavState(
        day=day,
        slate_date=slate,
        league=st.query_params.get("league"),
        game_id=st.query_params.get("game"),
        games_collapsed=st.query_params.get("games") == "off",
    )
