"""Prop-type filter pills for the opportunity feed (batter hits, SP strikeouts,
SP hits allowed, points, rebounds, assists), mirroring the league filter pills.

Display-only: filtering never changes what is recorded in the daily ledger. The
market taxonomy itself lives in ``domain.markets`` so the results breakdown
classifies markets identically.
"""

from __future__ import annotations

import streamlit as st

from domain.markets import LABELS, present_types, prop_type
from domain.models import Opportunity


def prop_type_of(opp: Opportunity) -> str:
    """Classify an opportunity by (league, market). Stable keys for filtering."""
    return prop_type(opp.league, opp.market)


def prop_type_of_row(row: dict) -> str:
    """Classify a graded results row (dict with ``league``/``market``)."""
    return prop_type(row.get("league"), row.get("market"))


def present_prop_types(opps: list[Opportunity]) -> list[str]:
    """Prop types present in these opportunities, in canonical order."""
    return present_types([(o.league, o.market) for o in opps])


def present_prop_types_rows(rows: list[dict]) -> list[str]:
    """Prop types present in these graded rows, in canonical order."""
    return present_types([(r.get("league"), r.get("market")) for r in rows])


def _state_key(prop_type_key: str, prefix: str = "") -> str:
    return f"{prefix}proptype_{prop_type_key}"


def render_prop_type_filters(present: list[str], *, key_prefix: str = "") -> None:
    """Render a pill per present prop type. Nothing when only one type exists.

    ``key_prefix`` namespaces the session-state keys so two surfaces (the Today
    feed and the Results view) keep independent selections.
    """
    for pt in present:
        st.session_state.setdefault(_state_key(pt, key_prefix), False)
    if len(present) <= 1:
        return
    row = st.container(horizontal=True, gap="small")
    for pt in present:
        key = _state_key(pt, key_prefix)
        active = bool(st.session_state.get(key, False))
        if row.button(LABELS.get(pt, pt), key=f"toggle_{key}",
                      type="primary" if active else "secondary", width="content"):
            st.session_state[key] = not active
            st.rerun()


def selected_prop_types(present: list[str], *, key_prefix: str = "") -> list[str]:
    """Prop types explicitly toggled on. Empty means 'show all'."""
    return [pt for pt in present if st.session_state.get(_state_key(pt, key_prefix), False)]
