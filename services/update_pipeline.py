"""The shared "rebuild everything" pipeline, used by both the CLI daily update and
the in-app uploader so there is one source of truth for what a refresh does:

    import the MLB feed → refresh WNBA + MLS → publish the DB to the cloud store.

Web-collector failures are captured (non-fatal) and returned in the summary; the
MLB import is the required step. Publishing is a no-op unless a bucket is configured.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

_REGRADE_DAYS = 7       # force-regrade this many recent days after an import
                        # (a week's buffer so a skipped update day can't strand a
                        #  still-pending slate outside the window)


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

    # Pick up an NFL season feed if one has been dropped in Downloads. Silent on the
    # common path (no feed, or the same feed as last time) and non-fatal on failure — a
    # bad NFL workbook must not take down the MLB daily update. In season this is what
    # keeps the slate↔feed bridge working on *this* year's games.
    try:
        from services.nfl_feed_refresh import refresh as refresh_nfl
        r = refresh_nfl()
        if r.status == "imported":
            out["nfl"] = {"seasons": list(r.seasons), "team_rows": r.team_rows,
                          "player_rows": r.player_rows, "message": r.message}
    except Exception as exc:
        out["nfl_error"] = str(exc)

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

    # How interesting the finished games actually were, so the editorial score has a
    # feedback loop rather than accumulating unchecked. Non-fatal: this is analysis,
    # and a network wobble must not fail the daily rebuild.
    try:
        from scripts.record_game_outcomes import run as record_outcomes
        out["game_outcomes"] = record_outcomes(days=_REGRADE_DAYS, verbose=False)
    except Exception as exc:
        out["game_outcomes_error"] = str(exc)

    # Build the public read model after every source has refreshed. This deliberately
    # moves network and Pandas work out of visitor requests; Django reads only SQLite.
    try:
        from services.daily_feed import precompute_days
        today = date.today()
        out["daily_feed"] = precompute_days([today, today + timedelta(days=1)])
    except Exception as exc:
        out["daily_feed_error"] = str(exc)

    try:
        from services.data_store import is_configured, publish_db
        if is_configured():
            # Publish the **slim** build, not the working database. The research tables
            # (NBA/CBB/NHL box scores, ~86% of the rows) are read by nothing in the app,
            # and a deployed copy is downloaded on every cold boot — 309MB against 107MB
            # on someone's phone. Falls back to the full file if the build fails, since a
            # stale deployment is worse than a large one.
            from scripts.build_deploy_db import build
            from src.config import DB_PATH
            try:
                slim = build(DB_PATH, DB_PATH.with_name("sportshub-deploy.db"))
            except Exception:                       # noqa: BLE001
                slim = None
            out["published"] = bool(publish_db(slim or DB_PATH))
            out["published_slim"] = slim is not None
        else:
            out["published"] = False
    except Exception as exc:
        out["publish_error"] = str(exc)
        out["published"] = False
    return out
