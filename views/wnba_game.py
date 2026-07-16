"""WNBA matchup page view.

Builds the immutable page model via the cached builder and renders each section
in the spec's order. No calculations here; sections that could not be computed
render empty and are skipped.
"""

from __future__ import annotations

import streamlit as st

from components import wnba_game as C
from domain.models import SlateGame
from router import NavState
from services.app_cache import cached_wnba_game_page
from services.wnba_game_page import ENGINE_VERSION


def render(nav: NavState, game: SlateGame) -> None:
    try:
        cache_key = f"{game.game_id}|{nav.slate_date.isoformat()}|{ENGINE_VERSION}"
        page = cached_wnba_game_page(cache_key, game, nav.slate_date.isoformat())
    except Exception as exc:  # never crash the whole app on a build error
        st.error("The WNBA matchup page could not be built.")
        st.exception(exc)
        return

    st.markdown(C.hero_html(page.hero), unsafe_allow_html=True)

    for html in (
        C.game_script_html(page.game_script),
        C.snapshot_html(page.away_snapshot, page.home_snapshot,
                        page.hero.away_team, page.hero.home_team),
        C.team_identity_html(page.away_identity, page.home_identity),
        C.battlefields_html(page.battlefields),
        C.shape_players_html(page.shape_players),
        C.trends_html(page.trending_up, page.trending_down),
        C.team_trends_html(page.away_trends, page.home_trends),
        C.opportunities_html(page.opportunities),
    ):
        if html:
            st.markdown(html, unsafe_allow_html=True)

    if page.data_status and page.data_status.detail:
        st.markdown(C.data_context_html(page.data_status.detail), unsafe_allow_html=True)
