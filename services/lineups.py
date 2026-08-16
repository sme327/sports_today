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
