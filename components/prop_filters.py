"""Prop-type filter pills for the opportunity feed (batter hits, SP strikeouts,
SP hits allowed, points, rebounds, assists), mirroring the league filter pills.

Display-only: filtering never changes what is recorded in the daily ledger.
"""

from __future__ import annotations

import streamlit as st

from domain.models import Opportunity

# Canonical order + display labels.
_PROP_TYPES: list[tuple[str, str]] = [
    ("hits", "Batter Hits"),
    ("sp_k", "SP Strikeouts"),
    ("sp_hits", "SP Hits Allowed"),
    ("points", "Points"),
    ("rebounds", "Rebounds"),
    ("assists", "Assists"),
]
_LABELS = dict(_PROP_TYPES)
_ORDER = [k for k, _ in _PROP_TYPES]


def prop_type_of(opp: Opportunity) -> str:
    """Classify an opportunity by (league, market). Stable keys for filtering."""
    m = (opp.market or "").lower()
    if opp.league == "MLB":
        if "strikeout" in m:
            return "sp_k"
        if "hits allowed" in m:
            return "sp_hits"
        return "hits"
    if "point" in m:
        return "points"
    if "rebound" in m:
        return "rebounds"
    if "assist" in m:
        return "assists"
    return "other"


def present_prop_types(opps: list[Opportunity]) -> list[str]:
    """Prop types present in these opportunities, in canonical order."""
    have = {prop_type_of(o) for o in opps}
    return [k for k in _ORDER if k in have]


def _state_key(prop_type: str) -> str:
    return f"proptype_{prop_type}"


def render_prop_type_filters(present: list[str]) -> None:
    """Render a pill per present prop type. Nothing when only one type exists."""
    for pt in present:
        st.session_state.setdefault(_state_key(pt), False)
    if len(present) <= 1:
        return
    row = st.container(horizontal=True, gap="small")
    for pt in present:
        key = _state_key(pt)
        active = bool(st.session_state.get(key, False))
        if row.button(_LABELS.get(pt, pt), key=f"toggle_{key}",
                      type="primary" if active else "secondary", width="content"):
            st.session_state[key] = not active
            st.rerun()


def selected_prop_types(present: list[str]) -> list[str]:
    """Prop types explicitly toggled on. Empty means 'show all'."""
    return [pt for pt in present if st.session_state.get(_state_key(pt), False)]
