"""MLB game page view (Phase 1).

Builds the immutable page model via the page service (cached) and renders each
section with the MLB components. No calculations happen here. Any section that
the builder could not compute simply renders empty and is skipped.
"""

from __future__ import annotations

import streamlit as st

from components import mlb_game as C
from components.opportunity_feed import opportunity_feed_html
from domain.models import SlateGame
from router import NavState
from services.app_cache import cached_mlb_game_page
from services.mlb_game_page import ENGINE_VERSION


def render(nav: NavState, game: SlateGame) -> None:
    try:
        cache_key = f"{game.game_id}|{nav.slate_date.isoformat()}|{ENGINE_VERSION}"
        page = cached_mlb_game_page(cache_key, game, nav.slate_date.isoformat())
    except Exception as exc:  # never crash the whole app on a build error
        st.error("The MLB game page could not be built.")
        st.exception(exc)
        return

    st.markdown(C.hero_html(page.hero), unsafe_allow_html=True)

    story = C.game_story_html(page.game_story)
    if story:
        st.markdown(story, unsafe_allow_html=True)

    st.markdown(C.team_identity_html(page.away_identity, page.home_identity), unsafe_allow_html=True)

    matchups = C.key_matchups_html(page.key_matchups)
    if matchups:
        st.markdown(matchups, unsafe_allow_html=True)

    st.markdown(C.player_trends_html(page.heating_up, page.cooling_off), unsafe_allow_html=True)

    # Players Positioned to Succeed — the shared opportunity feed (same scores as the slate).
    st.markdown('<div class="mlb-section"><div class="mlb-section-head">'
                '<h2>Players Positioned to Succeed</h2></div>', unsafe_allow_html=True)
    if page.opportunities:
        st.markdown(opportunity_feed_html(list(page.opportunities)), unsafe_allow_html=True)
    else:
        st.markdown('<div class="mlb-empty">No game-specific opportunities currently meet the '
                    'display threshold.</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    shape = C.game_shape_html(page.game_shape)
    if shape:
        st.markdown(shape, unsafe_allow_html=True)

    storylines = C.storylines_html(page.storylines)
    if storylines:
        st.markdown(storylines, unsafe_allow_html=True)

    if page.data_status and page.data_status.detail:
        st.markdown(C.data_context_html(page.data_status.detail), unsafe_allow_html=True)
