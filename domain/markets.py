"""Prop-market taxonomy — the single source of truth for classifying a market
into a stable prop-type key, shared by the opportunity feed filters (components)
and the results grading breakdown (services). No dependencies, so any layer may
import it without creating a cycle.
"""

from __future__ import annotations

# Canonical order + display labels. The order drives how filter pills and the
# per-market breakdown are laid out.
PROP_TYPES: list[tuple[str, str]] = [
    ("hits", "Batter Hits"),
    ("sp_k", "SP Strikeouts"),
    ("sp_hits", "SP Hits Allowed"),
    ("points", "Points"),
    ("rebounds", "Rebounds"),
    ("assists", "Assists"),
]
LABELS: dict[str, str] = dict(PROP_TYPES)
ORDER: list[str] = [k for k, _ in PROP_TYPES]


def prop_type(league: str | None, market: str | None) -> str:
    """Classify a (league, market) into a stable prop-type key.

    Market text is authoritative for MLB (a pitcher line names strikeouts or hits
    allowed; anything else is a batter hit) and for WNBA (points/rebounds/assists).
    Unrecognized markets fall to ``"other"``.
    """
    m = (market or "").lower()
    if league == "MLB":
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


def present_types(pairs: list[tuple[str | None, str | None]]) -> list[str]:
    """Prop types present among (league, market) pairs, in canonical order."""
    have = {prop_type(lg, mk) for lg, mk in pairs}
    return [k for k in ORDER if k in have]
