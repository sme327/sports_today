"""The shared "rebuild everything" pipeline, used by both the CLI daily update and
the in-app uploader so there is one source of truth for what a refresh does:

    import the MLB feed → refresh WNBA + MLS → publish the DB to the cloud store.

Web-collector failures are captured (non-fatal) and returned in the summary; the
MLB import is the required step. Publishing is a no-op unless a bucket is configured.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

_REGRADE_DAYS = 4       # force-regrade this many recent days after an import


def rebuild(feed_path: str | Path, *, collect_web: bool = True) -> dict:
    """Rebuild the DB from ``feed_path`` and refresh the web-collected leagues.
    Returns a summary dict: ``mlb`` counts always; ``wnba``/``mls`` (or
    ``*_error``) when ``collect_web``; ``published`` True if pushed to the store."""
    from src.ingest import import_feed

    out: dict = {}
    _, out["mlb"] = import_feed(feed_path)

    if collect_web:
        try:
            from src.wnba_collector import collect_wnba_season
            r = collect_wnba_season(season=date.today().year, end_date=date.today())
            out["wnba"] = {"games": r.games_downloaded, "rows": r.player_rows_written}
        except Exception as exc:
            out["wnba_error"] = str(exc)
        try:
            from src.mls_collector import collect as collect_mls
            m = collect_mls(season=date.today().year, verbose=False)
            out["mls"] = {"matches": m.events_collected, "standings": m.standings_rows}
        except Exception as exc:
            out["mls_error"] = str(exc)

    # Re-grade the last few days now that fresh results are loaded — corrects any
    # slate that was graded against partial data (the availability gate leaves such
    # rows pending, but a force pass also fixes any already frozen as void).
    try:
        from services import grading
        today = date.today()
        regraded = {}
        for i in range(1, _REGRADE_DAYS + 1):
            d = today - timedelta(days=i)
            s = grading.grade_slate(d, force=True)
            if s["graded"]:
                regraded[d.isoformat()] = {"hit": s["hit"], "miss": s["miss"], "void": s["void"]}
        out["regraded"] = regraded
    except Exception as exc:
        out["regrade_error"] = str(exc)

    try:
        from services.data_store import is_configured, publish_db
        out["published"] = bool(is_configured() and publish_db())
    except Exception as exc:
        out["publish_error"] = str(exc)
        out["published"] = False
    return out
