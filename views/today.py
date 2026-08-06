"""Today / Tomorrow page: slate, storyline status, and ranked opportunities.

Degraded-mode ordering (owner decision 3): live schedule -> cached slate ->
explicit, labeled league-wide fallback. A legitimately empty slate shows no
fallback. Slate opportunities are snapshotted once per day.
"""

from __future__ import annotations

import dataclasses

import streamlit as st

from components import empty_states
from components.date_switch import date_switch_html
from components.game_cards import games_toggle_html, group_games_by_state, schedule_grid_html
from components.league_filters import render_filters, selected_leagues
from components.navigation import day_label
from components.opportunity_feed import opportunity_feed_html
from components.prop_filters import (
    present_prop_types, prop_type_of, render_prop_type_filters, selected_prop_types,
)
from domain.models import DataStatus, Opportunity, OpportunityMode, SlateGame, SourceStatus
from leagues.base import LeagueAdapter, get_adapter, iter_adapters
from router import NavState
from services.app_cache import (cached_mlb_pitcher_opps, cached_mlb_tb_opps,
                                 cached_opportunities, cached_slate)
from services.freshness import get_freshness
from services import snapshots

# Leagues with connected opportunity analysis (others are schedule-only).
_ANALYSIS_LEAGUES = {"MLB", "WNBA"}
# Effectively-uncapped limit for the daily graded ledger (record every scored
# player, not just the displayed top 8).
_LEDGER_LIMIT = 100_000


def _mlb_import_affordance() -> None:
    """Optional, non-blocking MLB workbook import (sidebar). Shown only when no MLB
    data is loaded; the daily `update.command` / CLI path is the primary route, so
    the app never dead-ends when the feed is absent (e.g. on a fresh/cloud deploy)."""
    from pathlib import Path
    from src.config import CURRENT_FEED
    with st.expander("Load MLB data", expanded=False):
        st.caption("Live schedules work without this. Load the MLB feed to enable "
                   "1+ hit opportunities and the MLB matchup page.")
        feed = st.text_input("MLB workbook path", value=str(CURRENT_FEED))
        if st.button("Import workbook", type="primary", width="stretch"):
            try:
                from src.ingest import import_feed
                _, summary = import_feed(Path(feed).expanduser())
                st.success(f"Imported {summary['plate_appearances']:,} plate appearances "
                           f"from {summary['games']:,} games.")
                st.cache_data.clear()
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


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
            '<div class="page-title">Sports <span class="title-accent">Today</span></div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(date_switch_html(day, nav.games_collapsed), unsafe_allow_html=True)

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
        if not fresh.mlb_through:
            _mlb_import_affordance()

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
    # Sport filters (left) and the games collapse toggle (right) share one row.
    toggle_col = None
    if leagues_with_games:
        filter_col, toggle_col = st.columns([3, 1], vertical_alignment="center")
        with filter_col:
            render_filters(leagues_with_games)
    else:
        render_filters(leagues_with_games)  # no-op, preserves toggle state
    selected = selected_leagues(leagues_with_games)
    nothing_selected = not selected

    # Visible games per league honoring the filter.
    visible: dict[str, list[SlateGame]] = {}
    for adapter in leagues_with_games:
        league = adapter.league
        games = slates[league][0]
        visible[league] = games if (nothing_selected or league in selected) else []

    # Slate grid across leagues, grouped by state (live -> upcoming -> final),
    # chronological within each. No headers: the ordering and card treatment
    # carry the meaning. Empty groups are skipped, so the page reorganizes itself
    # as games transition — no filters, no user interaction.
    all_visible = [g for games in visible.values() for g in games]
    if all_visible:
        # Optional, sticky collapse of the schedule grid so the opportunity feed
        # is one glance away on a busy slate. Default is expanded.
        if toggle_col is not None:
            with toggle_col:
                st.markdown(games_toggle_html(day, nav.games_collapsed, len(all_visible)),
                            unsafe_allow_html=True)
        if not nav.games_collapsed:
            for group in group_games_by_state(all_visible):
                if group:
                    st.markdown(schedule_grid_html(group, day), unsafe_allow_html=True)
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
    # We score the FULL eligible population (not just the displayed top 8) so the
    # daily ledger can later grade the whole score distribution — the dataset for
    # calibration and finding signal we're missing. Display still shows the top 8.
    slate_opps: list[Opportunity] = []
    analysis_leagues: list[str] = []
    for league in _ANALYSIS_LEAGUES:
        games = visible.get(league) or []
        if not games:
            continue
        adapter = get_adapter(league)
        analysis_leagues.append(league)
        team_ids = tuple(sorted({t for g in games for t in g.team_identifiers}))
        opps = cached_opportunities(league, as_of_iso, OpportunityMode.SLATE.value,
                                    team_ids, limit=_LEDGER_LIMIT)
        slate_opps.extend(_stamp(opps, games, adapter))

    # MLB starting-pitcher props (SP strikeouts + SP hits allowed) for the slate's
    # probable starters — same feed / ledger / grading path as the batter props.
    mlb_games = visible.get("MLB") or []
    probables = tuple(sorted({
        (str(g.meta.get(key)), disp)
        for g in mlb_games
        for key, disp in (("away_pitcher", g.away_display), ("home_pitcher", g.home_display))
        if g.meta.get(key) and str(g.meta.get(key)).upper() != "TBD"
    }))
    if probables:
        pitcher_opps = cached_mlb_pitcher_opps(as_of_iso, probables)
        slate_opps.extend(_stamp(pitcher_opps, mlb_games, get_adapter("MLB")))

    # MLB batter Total-Bases props — same feed / ledger / grading path.
    if mlb_games:
        mlb_team_ids = tuple(sorted({t for g in mlb_games for t in g.team_identifiers}))
        tb_opps = cached_mlb_tb_opps(as_of_iso, mlb_team_ids)
        slate_opps.extend(_stamp(tb_opps, mlb_games, get_adapter("MLB")))

    slate_opps.sort(key=lambda o: o.sort_key, reverse=True)  # full set for the ledger

    if analysis_leagues:
        from services.data_store import is_configured
        # The in-app updater is only meaningful on a cloud deploy (a bucket to
        # publish to); locally the daily refresh is update.command.
        update_link = ('<a class="results-link" target="_self" href="?view=update">'
                       'Update data</a>') if is_configured() else ""
        st.markdown(
            '<div class="section-row"><h2>Top Opportunities</h2>'
            f'<span class="section-links">{update_link}'
            '<a class="results-link" target="_self" href="?view=results">'
            'Yesterday’s results →</a></span></div>',
            unsafe_allow_html=True,
        )
        # Prop-type pills (batter hits / SP strikeouts / SP hits allowed / …) filter
        # the DISPLAY only; the full population is still recorded below.
        present = present_prop_types(slate_opps)
        render_prop_type_filters(present)
        chosen = selected_prop_types(present)
        display_opps = [o for o in slate_opps if not chosen or prop_type_of(o) in chosen]
        top_slate = display_opps[:8]
        if top_slate:
            st.markdown(opportunity_feed_html(top_slate), unsafe_allow_html=True)
        else:
            empty_states.note(
                "No qualifying opportunities cleared the current role and sample "
                "requirements for the shown slate."
            )

    # Persist the day's FULL scored population with context (once per day) — the
    # graded ledger for long-term evaluation. Display used only the top 8 above.
    if slate_opps:
        status_map = {lg: slates[lg][1] for lg in analysis_leagues if slates.get(lg)}
        try:
            snapshots.write_daily_snapshot(
                slate_date=nav.slate_date,
                as_of=nav.slate_date,
                opportunities=slate_opps,
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
