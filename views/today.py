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


def _build_slate_opps(nav: NavState, visible: dict[str, list[SlateGame]]):
    """The full stamped slate opportunity population (batter hits + SP props + total
    bases), sorted. Built once and shared by the game-card strength scores and the
    Top Opportunities feed (underlying scorer calls are cached, so this is cheap)."""
    as_of_iso = nav.slate_date.isoformat()
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

    mlb_games = visible.get("MLB") or []
    probables = tuple(sorted({
        (str(g.meta.get(key)), disp)
        for g in mlb_games
        for key, disp in (("away_pitcher", g.away_display), ("home_pitcher", g.home_display))
        if g.meta.get(key) and str(g.meta.get(key)).upper() != "TBD"
    }))
    if probables:
        slate_opps.extend(_stamp(cached_mlb_pitcher_opps(as_of_iso, probables),
                                 mlb_games, get_adapter("MLB")))
    if mlb_games:
        mlb_team_ids = tuple(sorted({t for g in mlb_games for t in g.team_identifiers}))
        slate_opps.extend(_stamp(cached_mlb_tb_opps(as_of_iso, mlb_team_ids),
                                 mlb_games, get_adapter("MLB")))

    slate_opps.sort(key=lambda o: o.sort_key, reverse=True)
    return slate_opps, analysis_leagues


def _threshold_control_html(nav: NavState) -> str:
    """Global 'strong pick' bar (85+/90+/95+) near Top Opportunities. Changing it
    updates the 🔥 counts on every card (via the ?thr query param)."""
    pills = []
    for t in (85, 90, 95):
        active = " active" if nav.prop_threshold == t else ""
        q = f"?day={nav.day}&thr={t}" + (f"&focus={nav.focus_game}" if nav.focus_game else "")
        pills.append(f'<a class="thr-pill{active}" target="_self" href="{q}">{t}+</a>')
    return f'<span class="thr-control"><span class="thr-label">Strong pick</span>{"".join(pills)}</span>'


def _game_counts(slate_opps: list[Opportunity], threshold: int) -> dict[str, int]:
    """Per-game count of strong picks (score ≥ threshold) — the "🔥 N props X+" line
    on each card. Controlled by the global threshold near Top Opportunities."""
    from collections import defaultdict
    counts: dict[str, int] = defaultdict(int)
    for o in slate_opps:
        if o.game_id and o.opportunity_score >= threshold:
            counts[o.game_id] += 1
    return dict(counts)


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
    # Build the slate opportunities once — powers both the per-game strength scores
    # on the cards and the Top Opportunities feed below.
    slate_opps, analysis_leagues = _build_slate_opps(nav, visible)
    game_counts = _game_counts(slate_opps, nav.prop_threshold)
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
                    st.markdown(schedule_grid_html(group, day, game_counts, nav.prop_threshold),
                                unsafe_allow_html=True)
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

    _render_opportunities(nav, slates, slate_opps, analysis_leagues, all_visible)


def _render_opportunities(
    nav: NavState,
    slates: dict[str, tuple[list[SlateGame], DataStatus]],
    slate_opps: list[Opportunity],
    analysis_leagues: list[str],
    all_visible: list[SlateGame],
) -> None:
    # ``slate_opps`` is the full eligible population (already stamped + sorted),
    # built in render(); display shows the top 8, the ledger records everything.
    if analysis_leagues:
        from services.data_store import is_configured
        # The in-app updater is only meaningful on a cloud deploy (a bucket to
        # publish to); locally the daily refresh is update.command.
        update_link = ('<a class="results-link" target="_self" href="?view=update">'
                       'Update data</a>') if is_configured() else ""
        st.markdown(
            '<div id="opps" class="section-row"><h2>Top Opportunities</h2>'
            f'<span class="section-links">{_threshold_control_html(nav)}{update_link}'
            '<a class="results-link" target="_self" href="?view=results">'
            'Yesterday’s results →</a></span></div>',
            unsafe_allow_html=True,
        )
        # Focus filter: clicking a game card's 🔥 line narrows the feed to that game.
        focus = nav.focus_game
        game_label = {g.game_id: f"{g.away_display} @ {g.home_display}" for g in all_visible}
        if focus and focus in game_label:
            st.markdown(
                f'<div class="focus-chip"><span>Filtered to <b>{game_label[focus]}</b></span>'
                f'<a class="focus-clear" target="_self" href="?day={nav.day}">Clear ✕</a></div>',
                unsafe_allow_html=True)

        # Category pills classify the FOCUS-filtered set, so a single-game view never
        # offers dead-end categories (e.g. Points in a baseball game).
        base = [o for o in slate_opps if not focus or o.game_id == focus]
        present = present_prop_types(base)
        render_prop_type_filters(present)          # single-select, "All" default
        chosen = selected_prop_types(present)
        display_opps = [o for o in base if not chosen or prop_type_of(o) in chosen]
        # Full slate shows the top 8; a focused single game shows all its players.
        top_slate = display_opps if focus else display_opps[:8]
        st.markdown(f'<div class="opp-count">{len(display_opps)} '
                    f'{"opportunity" if len(display_opps) == 1 else "opportunities"}</div>',
                    unsafe_allow_html=True)
        if top_slate:
            st.markdown(opportunity_feed_html(top_slate), unsafe_allow_html=True)
        else:
            empty_states.note(
                "No qualifying opportunities cleared the current role and sample "
                "requirements for the shown slate."
            )
        # Data-quality caveat lives here (section level), separate from per-pick risk,
        # so a high score is never paired with a "we didn't model X" apology.
        st.markdown(
            '<div class="opp-disclaimer">Scores reflect recent player performance only. '
            'Opposing starter, park, weather, and bullpen are not modeled yet.</div>',
            unsafe_allow_html=True)

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
                games={g.game_id: g for g in all_visible},
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
