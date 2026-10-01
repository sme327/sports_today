"""Framework-independent short-lived cache for posted MLB lineups."""

from __future__ import annotations

from datetime import date
from threading import Lock
from time import monotonic

from src.mlb_lineups import EMPTY_LINEUPS, fetch_lineups

_TTL_SECONDS = 300
_cache: dict[str, tuple[float, object]] = {}
_lock = Lock()


def get_lineups(slate_date: date):
    key = slate_date.isoformat()
    now = monotonic()
    with _lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < _TTL_SECONDS:
            return cached[1]
    try:
        value = fetch_lineups(slate_date)
    except Exception:
        value = EMPTY_LINEUPS
    with _lock:
        _cache[key] = (now, value)
    return value


_order_cache: dict[tuple[str, str], tuple[float, object]] = {}


def get_last_order(team_id, slate_date: date):
    """``last_starting_order`` behind the same short-lived cache; ``None`` on any failure,
    so an unreachable StatsAPI falls back to the feed's order rather than to nothing."""
    from src.mlb_lineups import last_starting_order

    key = (str(team_id), slate_date.isoformat())
    now = monotonic()
    with _lock:
        cached = _order_cache.get(key)
        if cached and now - cached[0] < _TTL_SECONDS:
            return cached[1]
    try:
        value = last_starting_order(team_id, slate_date)
    except Exception:
        value = None
    with _lock:
        _order_cache[key] = (now, value)
    return value
