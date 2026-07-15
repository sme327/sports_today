"""Schedule fetching with degraded-mode ordering.

Owner decision 3 / refinement: live schedule first; on failure fall back to the
most recent valid cached slate for that date; only if neither yields games does
the caller consider a league-wide fallback. A successful-but-empty live response
is a legitimate off day (``EMPTY``) and must not trigger any fallback.
"""

from __future__ import annotations

from datetime import date, datetime

from domain.models import DataStatus, SlateGame, SourceStatus
from leagues.base import LeagueAdapter
from services import schedule_cache


def get_slate(
    adapter: LeagueAdapter,
    slate_date: date,
) -> tuple[list[SlateGame], DataStatus]:
    """Return games + provenance for one league on ``slate_date``.

    On a live success (even empty) the result is cached. On a live failure the
    latest usable cached slate is returned as ``CACHED``; if none exists the
    result is ``ERROR`` with no games.
    """
    now = datetime.now()
    try:
        games = adapter.fetch_schedule(slate_date)
    except Exception as exc:  # network/parse failure — try cache
        cached = schedule_cache.read_latest_usable(
            league=adapter.league, slate_date=slate_date
        )
        if cached is not None:
            games, fetched = cached
            return games, DataStatus(
                source=adapter.source_name,
                status=SourceStatus.CACHED,
                fetched_at=fetched,
                detail=f"Live schedule unavailable; showing cached slate. ({exc})",
            )
        return [], DataStatus(
            source=adapter.source_name,
            status=SourceStatus.ERROR,
            fetched_at=None,
            detail=f"Live schedule unavailable and no cached slate exists. ({exc})",
        )

    status = SourceStatus.LIVE if games else SourceStatus.EMPTY
    schedule_cache.write(
        league=adapter.league,
        slate_date=slate_date,
        source=adapter.source_name,
        status=status,
        games=games,
        fetched_at=now,
    )
    return games, DataStatus(
        source=adapter.source_name, status=status, fetched_at=now
    )
