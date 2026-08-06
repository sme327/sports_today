"""Prop-market registry — the single source of truth for every market a prop can be
scored, labeled, snapshotted, graded, and displayed in.

Two layers, both here so any code path stays consistent:

1. **Registry** (`MARKETS`, `MarketSpec`) — one entry per market *family* declaring
   its label, unit, source, direction rules, and prop-type. Behavior lives beside
   the data: `format_market` (canonical label text), `grade` (hit/miss comparison),
   `actual_display` (how the recorded stat reads), and `resolve` (legacy market
   *text* → structured `(key, direction)`, so the append-only snapshot ledger keeps
   grading without a rewrite).

2. **Filter taxonomy** (`PROP_TYPES`, `ORDER`, `LABELS`, `prop_type`, `present_types`)
   — the pill grouping used by the feed filters and the Results breakdown. Kept as a
   thin view over the registry (each spec carries its `prop_type`).

No dependencies, so any layer may import it without a cycle. Adding a market — MLB,
WNBA, or a future NFL prop — is one `MarketSpec` entry and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass

OVER = "over"     # graded hit when actual >= threshold
UNDER = "under"   # graded hit when actual <= threshold


@dataclass(frozen=True)
class MarketSpec:
    key: str                 # stable market-family id (stored on the snapshot)
    league: str              # "MLB" | "WNBA"
    prop_type: str           # filter-pill group (hits / sp_k / sp_hits / points / rebounds / assists)
    noun: str                # label noun: "Hit", "Strikeouts", "Hits Allowed", "Points" …
    unit: str                # actual-value word: "hit", "K", "hits allowed", "pts" …
    unit_plural: bool        # pluralize the unit for n != 1 ("hit" → "hits")
    source: str              # table the actual comes from
    default_direction: str   # OVER | UNDER
    allows_both: bool        # may this market be served over *and* under (SP props)?
    suffix: str = ""         # label suffix, e.g. " (SP)"
    engine_version: str = "mkt-v1"


# --- The registry. One entry per market family. -------------------------------
MARKETS: dict[str, MarketSpec] = {
    "batter_hit": MarketSpec(
        "batter_hit", "MLB", "hits", "Hit", "hit", True,
        "plate_appearances", OVER, allows_both=False),
    "batter_tb": MarketSpec(
        "batter_tb", "MLB", "tb", "Total Bases", "total bases", False,
        "plate_appearances", OVER, allows_both=False),
    "sp_k": MarketSpec(
        "sp_k", "MLB", "sp_k", "Strikeouts", "K", False,
        "plate_appearances", OVER, allows_both=True, suffix=" (SP)"),
    "sp_hits": MarketSpec(
        "sp_hits", "MLB", "sp_hits", "Hits Allowed", "hits allowed", False,
        "plate_appearances", UNDER, allows_both=True, suffix=" (SP)"),
    "wnba_points": MarketSpec(
        "wnba_points", "WNBA", "points", "Points", "pts", False,
        "wnba_player_game_logs", OVER, allows_both=False),
    "wnba_rebounds": MarketSpec(
        "wnba_rebounds", "WNBA", "rebounds", "Rebounds", "reb", False,
        "wnba_player_game_logs", OVER, allows_both=False),
    "wnba_assists": MarketSpec(
        "wnba_assists", "WNBA", "assists", "Assists", "ast", False,
        "wnba_player_game_logs", OVER, allows_both=False),
}

# WNBA scorers emit a bare stat key ("points"); map those to registry keys.
_WNBA_STAT_KEY = {"points": "wnba_points", "rebounds": "wnba_rebounds", "assists": "wnba_assists"}


def _fmt_threshold(threshold) -> str:
    if threshold is None:
        return ""
    return str(int(threshold)) if float(threshold).is_integer() else str(threshold)


def market_key_from_scorer(league: str, scorer_key: str) -> str | None:
    """Normalize a scorer's own key (``kind``/stat) to a registry key."""
    if scorer_key in MARKETS:
        return scorer_key
    if league == "WNBA":
        return _WNBA_STAT_KEY.get(scorer_key)
    return None


def format_market(key: str, threshold, direction: str | None = None) -> str:
    """Canonical market label — byte-identical to what the scorers emit today."""
    spec = MARKETS[key]
    direction = direction or spec.default_direction
    thr = _fmt_threshold(threshold)
    if direction == UNDER:
        return f"≤ {thr} {spec.noun}{spec.suffix}"
    return f"{thr}+ {spec.noun}{spec.suffix}"


def grade(key: str, actual: float, threshold, direction: str | None = None) -> str:
    """"hit" or "miss" for a recorded ``actual`` against ``threshold``."""
    spec = MARKETS[key]
    direction = direction or spec.default_direction
    thr = threshold if threshold is not None else (1 if key == "batter_hit" else 0)
    if direction == UNDER:
        return "hit" if actual <= thr else "miss"
    return "hit" if actual >= thr else "miss"


def actual_display(key: str | None, value) -> str:
    """How a recorded stat reads, e.g. "7 K", "2 hits", "22 pts"."""
    n = int(value) if float(value).is_integer() else value
    spec = MARKETS.get(key) if key else None
    if spec is None:
        return str(n)
    unit = spec.unit + "s" if (spec.unit_plural and n != 1) else spec.unit
    return f"{n} {unit}"


def resolve(league: str | None, market_text: str | None) -> tuple[str | None, str]:
    """Legacy market *text* → ``(market_key, direction)``. Formalizes the string
    parsing the codebase used before the registry, so historical snapshot rows (which
    store only text) still classify and grade. Direction is read from the ``≤`` prefix.

    Classification is by phrase (each market's noun is league-unique), so ``league``
    is advisory — resolution still works on a row that lost its league. Order matters:
    "hits allowed" must be tested before the bare "hit"."""
    m = (market_text or "").strip().lower()
    direction = UNDER if m.startswith("≤") else OVER
    if "strikeout" in m:
        return "sp_k", direction
    if "hits allowed" in m:
        return "sp_hits", direction
    if "total base" in m:
        return "batter_tb", OVER
    if "point" in m:
        return "wnba_points", OVER
    if "rebound" in m:
        return "wnba_rebounds", OVER
    if "assist" in m:
        return "wnba_assists", OVER
    if "hit" in m:                       # plain "N+ Hit" (batter), after "hits allowed"
        return "batter_hit", OVER
    return None, direction


def spec_for(league: str | None, market_text: str | None) -> MarketSpec | None:
    key, _ = resolve(league, market_text)
    return MARKETS.get(key) if key else None


# --- Filter taxonomy (pill grouping). A thin view over the registry. ----------
# Canonical order + display labels for the prop-type filter pills.
PROP_TYPES: list[tuple[str, str]] = [
    ("hits", "Batter Hits"),
    ("tb", "Total Bases"),
    ("sp_k", "SP Strikeouts"),
    ("sp_hits", "SP Hits Allowed"),
    ("points", "Points"),
    ("rebounds", "Rebounds"),
    ("assists", "Assists"),
]
LABELS: dict[str, str] = dict(PROP_TYPES)
ORDER: list[str] = [k for k, _ in PROP_TYPES]


def prop_type(league: str | None, market: str | None) -> str:
    """Classify a (league, market-text) into a filter-pill key. ``"other"`` if unknown."""
    spec = spec_for(league, market)
    return spec.prop_type if spec else "other"


def present_types(pairs: list[tuple[str | None, str | None]]) -> list[str]:
    """Prop types present among (league, market) pairs, in canonical order."""
    have = {prop_type(lg, mk) for lg, mk in pairs}
    return [k for k in ORDER if k in have]
