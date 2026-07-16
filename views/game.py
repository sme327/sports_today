"""Game view: a thin dispatcher.

Resolves the game by league + id, then delegates to the league's game page.
MLB has a dedicated page (views/mlb_game.py); leagues without a deep-dive render
a schedule-only placeholder. No league-specific analysis lives here.
"""

from __future__ import annotations

from html import escape

import streamlit as st

from components.format import format_game_time, logo_img
from components.navigation import back_href, day_label
from domain.models import SlateGame
from leagues.base import get_adapter
from router import NavState
from services.app_cache import cached_slate


def _find_game(league: str, slate_iso: str, game_id: str) -> SlateGame | None:
    try:
        games, _ = cached_slate(league, slate_iso)
    except Exception:
        return None
    return next((g for g in games if str(g.game_id) == str(game_id)), None)


def _detail_header(game: SlateGame) -> str:
    away = game.away_display
    home = game.home_display
    away_sub = game.away_name or away
    home_sub = game.home_name or home
    return (
        '<div class="detail-header">'
        f'<div class="detail-team">{logo_img(game.away_logo, away, "detail-logo")}'
        f'<div><div class="detail-name">{escape(away)}</div>'
        f'<div class="detail-sub">{escape(away_sub)}</div></div></div>'
        f'<div class="detail-at">@<div class="detail-sub">'
        f'{escape(format_game_time(game.start_time))}</div></div>'
        f'<div class="detail-team home"><div>'
        f'<div class="detail-name">{escape(home)}</div>'
        f'<div class="detail-sub">{escape(home_sub)}</div></div>'
        f'{logo_img(game.home_logo, home, "detail-logo")}</div>'
        '</div>'
    )


def render(nav: NavState) -> None:
    league = nav.league
    st.markdown(
        f'<a class="back-link" target="_self" href="{back_href(nav.day)}">'
        f'← Back to {day_label(nav.day).lower()}’s slate</a>',
        unsafe_allow_html=True,
    )

    game = _find_game(league, nav.slate_date.isoformat(), nav.game_id)
    if not game:
        st.error("This game could not be found for the selected date.")
        return

    # Dispatch to the league's game page. MLB and WNBA have dedicated pages.
    if league == "MLB":
        from views import mlb_game
        mlb_game.render(nav, game)
        return
    if league == "WNBA":
        from views import wnba_game
        wnba_game.render(nav, game)
        return

    # Leagues without a deep-dive: generic header + honest placeholder.
    st.markdown(_detail_header(game), unsafe_allow_html=True)
    adapter = get_adapter(league)
    label = league or "This league"
    if not adapter or not adapter.supports_deep_dive:
        st.info(
            f"{label} schedule navigation is live. "
            "Deeper team and player analysis is not connected yet."
        )
