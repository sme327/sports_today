"""Prop-type classification for the opportunity feed and the results breakdown.

Display-only: filtering never changes what is recorded in the daily ledger. The market
taxonomy itself lives in ``domain.markets`` so the results breakdown classifies markets
identically.

The Streamlit pill renderer that used to live here retired with the Streamlit app; the
static site builds its own filter chips from these helpers. What remains is pure — no UI
framework — which is why it survived the migration untouched.
"""

from __future__ import annotations

from domain.markets import LABELS, ORDER, prop_type_for
from domain.models import Opportunity


def prop_type_of(opp: Opportunity) -> str:
    """Classify an opportunity for filtering — by its stored market_key (structural),
    falling back to (league, market) text only when no key is present."""
    return prop_type_for(opp.market_key, opp.league, opp.market)


def prop_type_of_row(row: dict) -> str:
    """Classify a graded results row (dict with ``market_key``/``league``/``market``)."""
    return prop_type_for(row.get("market_key"), row.get("league"), row.get("market"))


def present_prop_types(opps: list[Opportunity]) -> list[str]:
    """Prop types present in these opportunities, in canonical order."""
    have = {prop_type_of(o) for o in opps}
    return [k for k in ORDER if k in have]


def present_prop_types_rows(rows: list[dict]) -> list[str]:
    """Prop types present in these graded rows, in canonical order."""
    have = {prop_type_of_row(r) for r in rows}
    return [k for k in ORDER if k in have]
