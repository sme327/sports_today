"""NFL season archive: browse a completed season by week and open any matchup's
deep-dive preview. ``?view=nfl`` lists weeks/games; ``?view=nfl&game=<id>`` opens the
matchup page. Driven by the ingested vendor data (not the live ESPN schedule)."""

from __future__ import annotations

from html import escape

import streamlit as st

from components import nfl_game as C
from router import NavState
from services.nfl_game_page import build_nfl_game_page, list_games, list_weeks


def _week_pills(weeks: list[dict], current: int) -> str:
    pills = ""
    for w in weeks:
        wk = int(w["week"])
        label = f"WC {wk}" if w["season_type"] == "postseason" else f"Wk {wk}"
        active = " active" if wk == current else ""
        pills += f'<a class="thr-pill{active}" target="_self" href="?view=nfl&wk={wk}">{label}</a>'
    return f'<div class="nfl-weeks">{pills}</div>'


def _game_card(g: dict) -> str:
    a, h = g["away_score"], g["home_score"]
    score = (f'<span class="nfl-arc-score">{a} – {h}</span>'
             if a is not None and h is not None else "")
    aw = "win" if (a is not None and h is not None and a > h) else ""
    hw = "win" if (a is not None and h is not None and h > a) else ""
    return (
        f'<a class="nfl-arc-game" target="_self" href="?view=nfl&game={escape(g["game_id"])}">'
        f'<span class="nfl-arc-team {aw}">{escape(g["away"])}</span>'
        f'<span class="nfl-arc-at">@</span>'
        f'<span class="nfl-arc-team home {hw}">{escape(g["home"])}</span>'
        f'{score}<span class="nfl-arc-go">→</span></a>'
    )


def render(nav: NavState) -> None:
    st.markdown('<div class="page-title">NFL <span class="title-accent">Archive</span></div>',
                unsafe_allow_html=True)

    weeks = list_weeks()
    if not weeks:
        st.info("No NFL season data loaded yet. Run `python -m scripts.import_nfl_feed`.")
        return

    # A specific matchup?
    if nav.game_id:
        page = None
        try:
            page = build_nfl_game_page(nav.game_id)
        except Exception as exc:
            st.error("This matchup could not be built.")
            st.exception(exc)
            return
        st.markdown('<a class="back-link" target="_self" href="?view=nfl">← Back to the season</a>',
                    unsafe_allow_html=True)
        if page is None:
            st.error("This game could not be found.")
            return
        st.markdown(C.page_html(page), unsafe_allow_html=True)
        return

    # The browser: week pills + that week's games.
    available = [int(w["week"]) for w in weeks]
    try:
        current = int(st.query_params.get("wk", available[0]))
    except (TypeError, ValueError):
        current = available[0]
    if current not in available:
        current = available[0]

    st.markdown(_week_pills(weeks, current), unsafe_allow_html=True)
    games = list_games(current)
    cards = "".join(_game_card(g) for g in games)
    st.markdown(f'<div class="nfl-arc-list">{cards}</div>', unsafe_allow_html=True)
