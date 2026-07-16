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
