"""Today / Tomorrow page: slate, storyline status, and ranked opportunities.

Degraded-mode ordering (owner decision 3): live schedule -> cached slate ->
explicit, labeled league-wide fallback. A legitimately empty slate shows no
fallback. Slate opportunities are snapshotted once per day.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import streamlit as st

from components import empty_states
from components.date_switch import date_switch_html
from components.game_cards import schedule_grid_html
from components.league_filters import render_filters, selected_leagues
from components.navigation import day_label, day_possessive
from components.opportunity_feed import opportunity_feed_html
from domain.models import DataStatus, Opportunity, OpportunityMode, SlateGame, SourceStatus
from leagues.base import LeagueAdapter, get_adapter, iter_adapters
from router import NavState
from services.app_cache import cached_opportunities, cached_slate
from services.freshness import get_freshness
from services import snapshots

# Leagues with connected opportunity analysis (others are schedule-only).
_ANALYSIS_LEAGUES = {"MLB", "WNBA"}


def _logo_map(games: list[SlateGame]) -> dict[str, str]:
    """Map every team identifier (name/short/abbr) to its logo url."""
    out: dict[str, str] = {}
    for g in games:
        for name, logo in (
            (g.away_name, g.away_logo), (g.away_short, g.away_logo), (g.away_abbr, g.away_logo),
            (g.home_name, g.home_logo), (g.home_short, g.home_logo), (g.home_abbr, g.home_logo),
        ):
            if name and logo:
                out[str(name)] = logo
    return out


def _game_id_map(games: list[SlateGame], adapter: LeagueAdapter) -> dict[str, str]:
    """Map a canonical team key to the game_id it plays in (best effort)."""
    out: dict[str, str] = {}
    for g in games:
        for ident in (g.away_name, g.away_abbr, g.home_name, g.home_abbr):
            key = adapter.match_team(ident)
            if key:
                out[key] = g.game_id
    return out


def _stamp(opps: list[Opportunity], games: list[SlateGame], adapter: LeagueAdapter) -> list[Opportunity]:
    """Attach team-logo fallback images and game ids without mutating cache."""
    logos = _logo_map(games)
    game_ids = _game_id_map(games, adapter)
    stamped: list[Opportunity] = []
    for o in opps:
        key = adapter.match_team(o.team_name)
        stamped.append(
            dataclasses.replace(
                o,
                image_url=o.image_url or logos.get(str(o.team_name)),
                game_id=o.game_id or (game_ids.get(key) if key else None),
            )
        )
    return stamped


def render(nav: NavState) -> None:
    day = nav.day
    slate_date = nav.slate_date

    # Header: title + same-tab date switch (original layout, unchanged).
    left, right = st.columns([4.4, 1.45], vertical_alignment="center")
    with left:
        st.markdown(
            f'<div class="page-title">'
            f'<span class="title-accent">{day_possessive(day)}</span> Sports Slate</div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(date_switch_html(day), unsafe_allow_html=True)

    # Sidebar: provenance / freshness.
    fresh = get_freshness()
    with st.sidebar:
        st.markdown("## 🟠 Sports Today")
        st.caption(f"Viewing {day_label(day).lower()} · {slate_date:%A, %B %-d}")
        if fresh.mlb_through:
            st.caption(f"MLB data through {fresh.mlb_through:%B %-d, %Y}")
        if fresh.wnba_through:
            st.caption(f"WNBA data through {fresh.wnba_through:%B %-d, %Y}")
        if st.button("Refresh cached data", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    # Fetch each league's slate (live -> cached -> error/empty).
    slates: dict[str, tuple[list[SlateGame], DataStatus]] = {}
    for adapter in iter_adapters():
        try:
            games, status = cached_slate(adapter.league, slate_date.isoformat())
        except Exception as exc:  # defensive: never crash the page on one league
            games, status = [], DataStatus(adapter.source_name, SourceStatus.ERROR, None, str(exc))
        slates[adapter.league] = (games, status)

    # League filter chips: only leagues that actually have games to show.
    leagues_with_games = [
        get_adapter(league)
        for league, (games, status) in slates.items()
        if games
    ]
    render_filters(leagues_with_games)
    selected = selected_leagues(leagues_with_games)
    nothing_selected = not selected

    # Visible games per league honoring the filter.
    visible: dict[str, list[SlateGame]] = {}
    for adapter in leagues_with_games:
        league = adapter.league
        games = slates[league][0]
        visible[league] = games if (nothing_selected or league in selected) else []

    # Chronological slate grid across leagues.
    all_visible = [g for games in visible.values() for g in games]
    all_visible.sort(key=lambda g: pd.to_datetime(g.start_time, utc=True, errors="coerce"))
    if all_visible:
        st.markdown(schedule_grid_html(all_visible, day), unsafe_allow_html=True)
    else:
        empty_states.no_games(day_label(day))

    # Degraded / error notices per shown-or-selected league.
    for league, (games, status) in slates.items():
        if status is None:
            continue
        relevant = nothing_selected or league in selected or games
        if not relevant:
            continue
        if status.status is SourceStatus.ERROR:
            empty_states.schedule_unavailable(status.source, status.detail)

    _render_opportunities(nav, slates, visible, nothing_selected, selected)


def _render_opportunities(
    nav: NavState,
    slates: dict[str, tuple[list[SlateGame], DataStatus]],
    visible: dict[str, list[SlateGame]],
    nothing_selected: bool,
    selected: list[str],
) -> None:
    as_of_iso = nav.slate_date.isoformat()

    # --- Primary slate opportunities (only leagues with visible games) ---
    slate_opps: list[Opportunity] = []
    analysis_leagues: list[str] = []
    for league in _ANALYSIS_LEAGUES:
        games = visible.get(league) or []
        if not games:
            continue
        adapter = get_adapter(league)
        analysis_leagues.append(league)
        team_ids = tuple(sorted({t for g in games for t in g.team_identifiers}))
        opps = cached_opportunities(league, as_of_iso, OpportunityMode.SLATE.value, team_ids)
        slate_opps.extend(_stamp(opps, games, adapter))

    slate_opps.sort(key=lambda o: o.sort_key, reverse=True)
    top_slate = slate_opps[:8]

    if analysis_leagues:
        st.markdown(
            '<div class="section-row"><h2>Top Opportunities</h2></div>',
            unsafe_allow_html=True,
        )
        if top_slate:
            st.markdown(opportunity_feed_html(top_slate), unsafe_allow_html=True)
        else:
            empty_states.note(
                "No qualifying opportunities cleared the current role and sample "
                "requirements for the shown slate."
            )

    # Persist the day's ranking with full context (once per day).
    if top_slate:
        status_map = {lg: slates[lg][1] for lg in analysis_leagues if slates.get(lg)}
        try:
            snapshots.write_daily_snapshot(
                slate_date=nav.slate_date,
                as_of=nav.slate_date,
                opportunities=top_slate,
                schedule_status=status_map,
            )
        except Exception:
            pass  # snapshotting must never break the page

    # --- Explicit degraded fallback: league-wide profiles ---
    # Only when a league's live schedule ERRORED with no usable cache (not EMPTY),
    # and the league is shown/selected. Never presented as today-specific.
    fallback_leagues = [
        league
        for league in _ANALYSIS_LEAGUES
        if slates.get(league)
        and slates[league][1] is not None
        and slates[league][1].status is SourceStatus.ERROR
        and (nothing_selected or league in selected)
    ]
    fallback_opps: list[Opportunity] = []
    for league in fallback_leagues:
        opps = cached_opportunities(league, as_of_iso, OpportunityMode.LEAGUE_WIDE.value, None)
        fallback_opps.extend(opps)
    fallback_opps.sort(key=lambda o: o.sort_key, reverse=True)
    if fallback_opps:
        st.markdown(
            '<div class="section-row"><h2>League-wide profiles — live slate unavailable</h2>'
            '<span class="section-count">not today-specific</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown(opportunity_feed_html(fallback_opps[:8]), unsafe_allow_html=True)
