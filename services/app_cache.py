"""Streamlit caching layer over schedule fetching and opportunity scoring.

Keeps the heavy work (network schedule calls, SQLite scans) off the hot path so
reruns triggered by filter clicks don't refetch everything (addresses Risk R2).
Pure services stay Streamlit-free; caching lives only here.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from domain.models import DataStatus, Opportunity, OpportunityMode, SlateGame
from leagues.base import get_adapter
from services.schedules import get_slate


@st.cache_data(ttl=120, show_spinner=False)
def cached_slate(league: str, slate_iso: str) -> tuple[list[SlateGame], DataStatus]:
    adapter = get_adapter(league)
    return get_slate(adapter, date.fromisoformat(slate_iso))


@st.cache_data(ttl=900, show_spinner=False)
def cached_mlb_game_page(cache_key: str, _game, as_of_iso: str):
    """Build the MLB game page model, cached by cache_key.

    ``_game`` is prefixed with ``_`` so Streamlit does not try to hash the
    SlateGame; ``cache_key`` (game id + as_of + engine version) drives caching.
    """
    from datetime import date
    from services.mlb_game_page import build_mlb_game_page
    d = date.fromisoformat(as_of_iso)
    return build_mlb_game_page(_game, d, d)


@st.cache_data(ttl=900, show_spinner=False)
def cached_wnba_game_page(cache_key: str, _game, as_of_iso: str):
    """Build the WNBA matchup page model, cached by cache_key (see cached_mlb_game_page)."""
    from datetime import date
    from services.wnba_game_page import build_wnba_game_page
    d = date.fromisoformat(as_of_iso)
    return build_wnba_game_page(_game, d, d)


@st.cache_data(ttl=900, show_spinner=False)
def cached_mls_game_page(cache_key: str, _game, as_of_iso: str):
    """Build the MLS matchup page model, cached by cache_key (see cached_mlb_game_page)."""
    from datetime import date
    from services.mls_game_page import build_mls_game_page
    d = date.fromisoformat(as_of_iso)
    return build_mls_game_page(_game, d, d)


@st.cache_data(ttl=300, show_spinner=False)
def cached_lineups(slate_iso: str):
    """Today's posted MLB batting lineups, cached with a short TTL so late-posted
    lineups get picked up on refresh. Degrades to empty on any network error."""
    from src.mlb_lineups import EMPTY_LINEUPS, fetch_lineups
    try:
        return fetch_lineups(date.fromisoformat(slate_iso))
    except Exception:
        return EMPTY_LINEUPS


@st.cache_data(ttl=900, show_spinner=False)
def cached_mlb_tb_opps(as_of_iso: str, team_ids: tuple[str, ...], limit: int = 100_000):
    """Batter Total-Bases opportunities for the slate, cached by (as_of, teams)."""
    adapter = get_adapter("MLB")
    return adapter.tb_opportunities(
        as_of=date.fromisoformat(as_of_iso), scheduled_team_ids=list(team_ids), limit=limit)


@st.cache_data(ttl=900, show_spinner=False)
def cached_mlb_kbb_opps(as_of_iso: str, team_ids: tuple[str, ...], limit: int = 100_000):
    """Batter strikeout + walk opportunities for the slate, cached by (as_of, teams)."""
    adapter = get_adapter("MLB")
    return adapter.k_bb_opportunities(
        as_of=date.fromisoformat(as_of_iso), scheduled_team_ids=list(team_ids), limit=limit)


@st.cache_data(ttl=900, show_spinner=False)
def cached_mlb_pitcher_opps(as_of_iso: str, probables: tuple[tuple[str, str], ...]):
    """SP strikeout + hits-allowed opportunities for the slate's probable starters,
    cached by (as_of, probable pitchers)."""
    from services.data_access import load_plate_appearances
    from services.mlb_pitcher_props import build_pitcher_opportunities
    d = date.fromisoformat(as_of_iso)
    pa = load_plate_appearances(as_of=d)
    return build_pitcher_opportunities(pa, [tuple(p) for p in probables], d)


@st.cache_data(ttl=900, show_spinner=False)
def cached_opportunities(
    league: str,
    as_of_iso: str,
    mode_value: str,
    team_ids: tuple[str, ...] | None = None,
    limit: int = 8,
) -> list[Opportunity]:
    adapter = get_adapter(league)
    return adapter.opportunities(
        as_of=date.fromisoformat(as_of_iso),
        scheduled_team_ids=list(team_ids) if team_ids else None,
        mode=OpportunityMode(mode_value),
        limit=limit,
    )
