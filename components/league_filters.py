"""Independent league on/off filter chips.

Preserves the existing behavior: each league is an independent toggle stored in
session state (keys ``show_mlb`` / ``show_wnba`` / ``show_world_cup``). When none
is selected, every league with games that day is shown.
"""

from __future__ import annotations

import streamlit as st

from leagues.base import LeagueAdapter


def state_key(league: str) -> str:
    return "show_" + league.lower().replace(" ", "_")


def render_filters(leagues_with_games: list[LeagueAdapter]) -> None:
    for adapter in leagues_with_games:
        st.session_state.setdefault(state_key(adapter.league), False)
    if not leagues_with_games:
        return
    ratios = [1] * len(leagues_with_games) + [max(1, 7 - len(leagues_with_games))]
    cols = st.columns(ratios, gap="small")
    for col, adapter in zip(cols, leagues_with_games):
        with col:
            key = state_key(adapter.league)
            active = bool(st.session_state.get(key, False))
            if st.button(
                adapter.label,
                key=f"toggle_{key}",
                type="primary" if active else "secondary",
                width="content",
            ):
                st.session_state[key] = not active
                st.rerun()


def selected_leagues(leagues_with_games: list[LeagueAdapter]) -> list[str]:
    """Leagues explicitly toggled on. Empty means 'show all'."""
    return [
        a.league
        for a in leagues_with_games
        if st.session_state.get(state_key(a.league), False)
    ]
