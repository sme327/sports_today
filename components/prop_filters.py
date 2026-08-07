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


def _sel_key(prefix: str) -> str:
    return f"{prefix}proptype_sel"


def render_prop_type_filters(present: list[str], *, key_prefix: str = "") -> None:
    """Single-select category pills with an explicit **All** (the default, active when
    nothing else is chosen). The selected category is clearly highlighted. Nothing is
    shown when there's only one category to choose from.

    ``key_prefix`` namespaces the session-state key so two surfaces (the Today feed
    and the Results view) keep independent selections.
    """
    key = _sel_key(key_prefix)
    st.session_state.setdefault(key, "all")
    # A category that's no longer present (e.g. after focusing a game) → back to All.
    if st.session_state[key] != "all" and st.session_state[key] not in present:
        st.session_state[key] = "all"
    if len(present) < 2:
        return
    active = st.session_state[key]
    row = st.container(horizontal=True, gap="small")
    if row.button("All", key=f"{key_prefix}pt_all",
                  type="primary" if active == "all" else "secondary", width="content"):
        if active != "all":
            st.session_state[key] = "all"
            st.rerun()
    for pt in present:
        if row.button(LABELS.get(pt, pt), key=f"{key_prefix}pt_{pt}",
                      type="primary" if active == pt else "secondary", width="content"):
            if active != pt:
                st.session_state[key] = pt
                st.rerun()


def selected_prop_types(present: list[str], *, key_prefix: str = "") -> list[str]:
    """The chosen category as a one-item list, or empty for 'All'."""
    sel = st.session_state.get(_sel_key(key_prefix), "all")
    return [] if (sel == "all" or sel not in present) else [sel]
