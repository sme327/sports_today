"""Game deep-dive view.

MLB games get Teams and Players tabs. Leagues whose adapter does not yet support
deep analysis render a schedule-only placeholder. All historical windows use data
strictly before the slate date (as_of), consistent with the leakage policy.
"""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from components.format import format_game_time, logo_img
from components.navigation import back_href, day_label
from domain.models import SlateGame
from leagues.base import get_adapter
from router import NavState
from services.app_cache import cached_slate
from services.data_access import load_plate_appearances
from src.metrics import hitter_game_logs, team_recent
from src.opportunity import score_hit_opportunities


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

    st.markdown(_detail_header(game), unsafe_allow_html=True)

    adapter = get_adapter(league)
    if not adapter or not adapter.supports_deep_dive:
        label = league or "This league"
        st.info(
            f"{label} schedule navigation is live. "
            "Deeper team and player analysis is not connected yet."
        )
        return

    _render_mlb_deep_dive(game, nav)


def _render_mlb_deep_dive(game: SlateGame, nav: NavState) -> None:
    pa = load_plate_appearances(as_of=nav.slate_date)
    teams = [t for t in (game.away_name, game.home_name) if t]
    teams_tab, players_tab = st.tabs(["Teams", "Players"])

    with teams_tab:
        cols = st.columns(2)
        for col, team in zip(cols, teams):
            with col:
                metrics = team_recent(pa, team, 10) if not pa.empty else {}
                st.subheader(team)
                if not metrics:
                    st.caption("No recent team data available.")
                else:
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Hits/game", f"{metrics['hits_per_game']:.1f}")
                    m2.metric("TB/game", f"{metrics['tb_per_game']:.1f}")
                    m3.metric("K rate", f"{metrics['k_rate']:.1%}")
                    st.caption(f"Last {metrics['games']} games")
        st.warning(
            "Sides and totals analysis will improve after probable pitchers, "
            "bullpen freshness, park, and weather are included."
        )

    with players_tab:
        opp = score_hit_opportunities(pa, teams) if not pa.empty else pd.DataFrame()
        if opp.empty:
            st.info("No qualifying opportunities were found.")
            return
        for _, row in opp.head(10).iterrows():
            support = list(row.support) if isinstance(row.support, list) else []
            risks = list(row.risks) if isinstance(row.risks, list) else []
            with st.expander(f"{int(row.opportunity_score)} · {row.player} — {row.market}"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Opportunity", int(row.opportunity_score))
                c2.metric("Stability", int(row.stability_score))
                c3.metric("Last 25 PA hit rate", f"{row.last_25_hit_rate:.0%}")
                c4.metric("PA/game", f"{row.pa_per_game:.2f}")
                st.markdown("**Why it stands out**")
                st.write(" · ".join(support) if support else "Current-season contact profile supports further review.")
                st.markdown("**What could go wrong**")
                st.write(" · ".join(risks) if risks else "Opponent and confirmed lineup context are incomplete.")
                logs = hitter_game_logs(pa, int(row.batter_id), 10).copy()
                if not logs.empty:
                    logs["game_date"] = pd.to_datetime(logs["game_date"]).dt.strftime("%b %-d")
                    logs = logs.rename(columns={
                        "game_date": "Date", "pitching_team": "Opponent", "pa": "PA",
                        "hits": "H", "total_bases": "TB", "walks": "BB",
                        "strikeouts": "K", "home_runs": "HR",
                    })
                    st.dataframe(
                        logs[["Date", "Opponent", "PA", "H", "TB", "BB", "K", "HR"]],
                        width="stretch", hide_index=True,
                    )
