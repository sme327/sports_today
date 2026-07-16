"""MLS matchup page view.

Builds the immutable page model via the cached builder and renders each section
in the blueprint's order. No calculations here; sections carry their own data
state and always render (honest placeholders instead of disappearing).
"""

from __future__ import annotations

import streamlit as st

from components import mls_game as C
from domain.models import SlateGame
from router import NavState
from services.app_cache import cached_mls_game_page
from services.mls_game_page import ENGINE_VERSION


def render(nav: NavState, game: SlateGame) -> None:
    try:
        cache_key = f"{game.game_id}|{nav.slate_date.isoformat()}|{ENGINE_VERSION}"
        page = cached_mls_game_page(cache_key, game, nav.slate_date.isoformat())
    except Exception as exc:  # never crash the whole app on a build error
        st.error("The MLS matchup page could not be built.")
        st.exception(exc)
        return

    st.markdown(C.hero_html(page.hero), unsafe_allow_html=True)

    for html in (
        C.snapshot_html(page.snapshot, page.hero.away.short, page.hero.home.short),
        C.tactical_html(page.tactical),
        C.storylines_html(page.storylines),
        C.lineups_html(page.lineups),
        C.players_html(page.players),
        C.attacking_html(page.attacking),
        C.discipline_html(page.discipline),
        C.timeline_html(page.timeline),
        C.honest_gaps_html(page.honest_gaps),
    ):
        if html:
            st.markdown(html, unsafe_allow_html=True)

    if page.data_status and page.data_status.detail:
        st.markdown(C.data_context_html(page.data_status.detail), unsafe_allow_html=True)
