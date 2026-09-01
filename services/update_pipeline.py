"""The shared "rebuild everything" pipeline behind the daily update, so there is
one source of truth for what a refresh does:

    import the MLB feed → refresh WNBA + MLS (+ NFL pickup) → regrade → precompute
    → publish the DB to the cloud store.

Web-collector failures are captured (non-fatal) and returned in the summary; the
MLB import is the required step. Publishing is a no-op unless a bucket is configured.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

_REGRADE_DAYS = 7       # force-regrade this many recent days after an import
                        # (a week's buffer so a skipped update day can't strand a
                        #  still-pending slate outside the window)

SLATE_DAYS = 3          # slate days to precompute, starting today. The third is the
                        # back pocket the browser promotes when the calendar rolls past
                        # the build date — it must equal len(web.today.DAY_OFFSETS),
                        # which a test asserts, since services may not import web.


# August through January: college football's calendar, plus the bowl tail.
_NCAAF_MONTHS = {8, 9, 10, 11, 12, 1}


def rebuild(feed_path: str | Path, *, collect_web: bool = True,
            import_mlb: bool = True) -> dict:
    """Rebuild the DB from ``feed_path`` and refresh the web-collected leagues.
    Returns a summary dict: ``mlb`` counts when the feed was imported;
    ``wnba``/``mls`` (or ``*_error``) when ``collect_web``; ``published`` True if
    pushed to the store.

    ``import_mlb=False`` skips the workbook import and leaves the existing database
    alone. Everything after it — collectors, regrading, the precomputed slates — still
    runs, because today's and tomorrow's games come from the schedule sources, not from
    the MLB feed. That is what makes the site refreshable on a morning when the vendor
    file has not arrived, or has not been downloaded yet.
    """
    out: dict = {}
    if import_mlb:
        from src.ingest import import_feed
        _, out["mlb"] = import_feed(feed_path)

    def _collect_wnba() -> dict:
        from src.wnba_collector import collect_wnba_season
        r = collect_wnba_season(season=date.today().year, end_date=date.today())
        return {"games": r.games_downloaded, "rows": r.player_rows_written}

    def _collect_mls() -> dict:
        from src.mls_collector import collect as collect_mls
        m = collect_mls(season=date.today().year, verbose=False)
        return {"matches": m.events_collected, "standings": m.standings_rows}

    def _refresh_nfl() -> dict | None:
        # Pick up an NFL season feed if one has been dropped in Downloads. Silent on
        # the common path (no feed, or the same feed as last time) and non-fatal on
        # failure — a bad NFL workbook must not take down the MLB daily update. In
        # season this is what keeps the slate↔feed bridge working on *this* year's games.
        from services.nfl_feed_refresh import refresh as refresh_nfl
        r = refresh_nfl()
        if r.status != "imported":
            return None
        return {"seasons": list(r.seasons), "team_rows": r.team_rows,
                "player_rows": r.player_rows, "message": r.message}

    def _refresh_ncaaf() -> dict | None:
        # College football's season context: last season's records, that season's
        # leading passer and where he is now. Season-stable, so the collector skips any
        # team checked in the last week and most days this does nothing at all. Only
        # runs in football months — there is no reason to ask about college rosters in
        # May — and is non-fatal like the rest.
        today = date.today()
        if today.month not in _NCAAF_MONTHS:
            return None
        from src.ncaaf_collector import collect as collect_ncaaf
        prior = today.year - 1 if today.month >= 3 else today.year - 2
        r = collect_ncaaf(prior_season=prior, current_season=prior + 1, pause=0.02)
        if not r.get("teams"):
            return None                  # everything already fresh; stay quiet
        return {"teams": r["teams"], "passers": r["passers"],
                "records": r["team_seasons"], "skipped": r["skipped"]}

    def _refresh_prior_seasons() -> dict | None:
        # Completed NHL/NBA seasons, so an opening-night slate can be ranked at all.
        # Two requests, and a finished season never changes, so this is a no-op once
        # stored. The season is resolved 30 days ahead: in August the useful "prior"
        # season is the one the *upcoming* season looks back on, not the one today's
        # (empty) calendar sits in.
        from datetime import timedelta

        from services.prior_season import prior_season_year
        from src.prior_season_collector import LEAGUES, collect, have_season
        season = prior_season_year(date.today() + timedelta(days=30))
        missing = [lg for lg in LEAGUES if not have_season(lg, season)]
        if not missing:
            return None
        got = collect(season=season, leagues=missing)
        return {"season": season, **got}

    # The collectors are independent and dominated by network wait, so they run
    # concurrently. They all write to the one SQLite file, but to disjoint tables in
    # short transactions — SQLite serializes writers with a 5s busy timeout, and a
    # collector that loses that race fails non-fatally and retries tomorrow.
    tasks: list[tuple[str, Callable[[], dict | None]]] = []
    if collect_web:
        tasks += [("wnba", _collect_wnba), ("mls", _collect_mls)]
    tasks.append(("nfl", _refresh_nfl))
    if collect_web:
        tasks.append(("ncaaf", _refresh_ncaaf))
        tasks.append(("prior_seasons", _refresh_prior_seasons))
    with ThreadPoolExecutor(max_workers=len(tasks), thread_name_prefix="collect") as pool:
        futures = [(key, pool.submit(fn)) for key, fn in tasks]
        for key, future in futures:
            try:
                value = future.result()
                if value is not None:
                    out[key] = value
            except Exception as exc:
                out[f"{key}_error"] = str(exc)

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
                # grade_slate counts snapshot *rows*, and a slate precomputed the day
                # before holds two captures of every prop — so those counts run ~2x the
                # day's actual record, and the terminal disagreed with the Results page
                # about the same day. Report the deduped props through the one definition
                # both surfaces already share.
                record = grading.tally(grading.load_graded_slate(d))
                regraded[d.isoformat()] = {"hit": record["hit"], "miss": record["miss"],
                                           "void": record["void"]}
        out["regraded"] = regraded
    except Exception as exc:
        out["regrade_error"] = str(exc)

    # Current standings — the reference point a style read cannot give. Four cheap
    # requests, and like every other collector here it is non-fatal: context must never
    # fail a data run, and a matchup page without a record is merely quieter.
    try:
        from src.standings_collector import collect as collect_standings
        out["standings"] = collect_standings()
    except Exception as exc:
        out["standings_error"] = str(exc)

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
        # Three days, not two. The site is static, so at the viewer's midnight every
        # page is still describing the build date until something rebuilds it — and the
        # rebuild cannot be scheduled here (macOS refuses launchd read access to this
        # project's folder; see scripts/nightly_refresh.sh). Precomputing a third day
        # instead lets the *browser* roll the slate over: yesterday's "tomorrow" becomes
        # today, and this third day becomes tomorrow. Buys two rollovers, which covers a
        # run that lands at midday rather than at dawn.
        # Deliberately not imported from web.today.DAY_OFFSETS: services must not import
        # the web layer (test_layering). The two are asserted equal by a test instead.
        out["daily_feed"] = precompute_days(
            [today + timedelta(days=offset) for offset in range(SLATE_DAYS)])
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
