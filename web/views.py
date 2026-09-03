from __future__ import annotations

from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from web.today import build_context
from web.analytics import performance_context, results_context
from web.games import find_game, mlb_context, mls_context, wnba_context
from web.nfl import archive_context, matchup_context
from services.daily_feed import load_cached_schedules, refresh_schedules


def health(request):
    return JsonResponse({"status": "ok", "service": "sports-today"})


def results(request):
    return render(
        request,
        "web/results.html",
        results_context(request.GET, timezone.localdate()),
    )


def performance(request):
    return render(
        request,
        "web/performance.html",
        performance_context(request.GET, timezone.localdate()),
    )


def nfl_archive(request):
    return render(request, "web/nfl_archive.html", archive_context(request.GET))


def nfl_matchup(request, game_id: str):
    context = matchup_context(game_id)
    if context is None:
        raise Http404("NFL game not found in the loaded season archive")
    response = render(request, "web/nfl_matchup.html", context)
    response["Server-Timing"] = f"matchup;dur={context['build_ms']}"
    response["X-Sports-Today-Cache"] = context["cache_source"]
    return response


def game(request, league: str, game_id: str):
    from web.today import parse_day
    from web.simple_game import simple_game_context

    day, slate_date = parse_day(request.GET.get("day"), timezone.localdate())
    league = league.upper()
    slate_game = find_game(league, game_id, slate_date)
    if slate_game is None:
        raise Http404("Game not found in the cached slate")
    if league == "NFL":
        from services.nfl_bridge import feed_game_id
        from web.nfl import pregame_context

        archive_id = feed_game_id(slate_game)
        if archive_id:
            # Played and in the feed: the game's own page, with its analysis.
            return redirect("nfl-matchup", game_id=archive_id)
        # Upcoming (the feed holds only played games, so pregame never matches):
        # a page built from aggregated data describing tonight's teams.
        context = pregame_context(slate_game, slate_date)
        if context is not None:
            context["day"] = day
            response = render(request, "web/nfl_matchup.html", context)
            response["Server-Timing"] = f"matchup;dur={context['build_ms']}"
            response["X-Sports-Today-Cache"] = context["cache_source"]
            return response
    if league not in {"MLB", "WNBA", "MLS"}:
        return render(request, "web/game_simple.html",
                      simple_game_context(slate_game, slate_date, day))
    builders = {"MLB": mlb_context, "WNBA": wnba_context, "MLS": mls_context}
    context = builders[league](slate_game, slate_date)
    context["day"] = day
    response = render(request, "web/matchup.html", context)
    response["Server-Timing"] = f"matchup;dur={context['build_ms']}"
    response["X-Sports-Today-Cache"] = context["cache_source"]
    return response


def today(request):
    context = build_context(request.GET, timezone.localdate())
    context["refresh_query"] = request.GET.urlencode()
    response = render(request, "web/today.html", context)
    timing = context.get("timing") or {}
    response["Server-Timing"] = (
        f"schedule;dur={timing.get('schedule_ms', 0)}, "
        f"feed;dur={timing.get('feed_ms', 0)}, "
        f"app;dur={timing.get('total_ms', 0)}"
    )
    return response


def schedule_fragment(request):
    """Refresh stale schedules after first paint, never on the initial HTML path."""
    from datetime import datetime, timedelta
    from web.today import parse_day

    _, slate_date = parse_day(request.GET.get("day"), timezone.localdate())
    cached = load_cached_schedules(slate_date)
    cutoff = datetime.now() - timedelta(seconds=120)
    stale = any(
        status.fetched_at is None or status.fetched_at < cutoff
        for _, status in cached.values()
    )
    lock_key = f"schedule-refresh:{slate_date.isoformat()}"
    if stale and cache.add(lock_key, True, timeout=110):
        try:
            refresh_schedules(slate_date)
        finally:
            cache.delete(lock_key)
    context = build_context(request.GET, timezone.localdate())
    return render(request, "web/_schedule.html", context)


def standings(request):
    """Per-league standings. The league is a query param rather than a path segment so
    the static export gives each one its own directory without a new route shape."""
    from web.standings_view import build_context as standings_context

    context = standings_context(request.GET.get("league"), timezone.localdate())
    return render(request, "web/standings.html", context)


# The two leagues that have a trends page. MLB first: it is the deeper data and the
# default the menu points at.
_TRENDING_LEAGUES = ("MLB", "WNBA")


def trending(request):
    """League-wide form. Both leagues render through one template because
    services/wnba_trending deliberately mirrors mlb_trending's card contract."""
    league = (request.GET.get("league") or "MLB").upper()
    if league not in _TRENDING_LEAGUES:
        league = "MLB"
    if league == "WNBA":
        from services.wnba_trending import build_context
    else:
        from services.mlb_trending import build_context
    context = build_context(timezone.localdate())
    context["leagues"] = list(_TRENDING_LEAGUES)
    return render(request, "web/trending.html", context)


# Leagues with a race page. Each has its own builder because the formats differ
# structurally — MLB seeds six per league from divisions plus wild cards, the WNBA seeds
# eight across one table — and forcing one through the other would invent structure.
_PLAYOFF_LEAGUES = ("MLB", "WNBA")


def playoffs(request):
    league = (request.GET.get("league") or "MLB").upper()
    if league not in _PLAYOFF_LEAGUES:
        league = "MLB"
    if league == "WNBA":
        from services.wnba_playoffs import build_context
    else:
        from services.mlb_playoffs import build_context
    context = build_context(timezone.localdate())
    # Only offer a league whose race is actually showable, so the switch never lands on
    # an empty page.
    from services import playoff_window, standings
    context["leagues"] = [
        lg for lg in _PLAYOFF_LEAGUES
        if playoff_window.state(lg, standings.for_league(lg)) in ("live", "final")
    ]
    _link_matchups(context.get("games") or [], league, timezone.localdate())
    return render(request, "web/playoffs.html", context)


def _link_matchups(games: list[dict], league: str, today) -> None:
    """Point a race game at its matchup page, where one exists.

    A game only has a page if it is on one of the precomputed slate days, so the slate's
    own schedules are the authority — and the link has to carry the *same* `day` slug the
    card uses, because the exporter keys a matchup page on its full query string. Guessing
    the slug would produce a URL that resolves locally and 404s on the published site.

    Most of this list is a week or two out and has no page; those stay plain text rather
    than becoming links to a page that does not exist.
    """
    from datetime import timedelta

    from services import daily_feed
    from web.today import DAY_OFFSETS

    slug_for: dict[str, str] = {}
    for slug, offset in DAY_OFFSETS.items():
        slate = daily_feed.load_cached_schedules(today + timedelta(days=offset))
        for game in (slate.get(league, ([], None))[0] or []):
            slug_for.setdefault(str(game.game_id), slug)

    for game in games:
        slug = slug_for.get(str(game.get("game_id")))
        game["matchup"] = (
            f"/game/{league}/{game['game_id']}/?day={slug}" if slug else ""
        )


def nfl_schedule(request):
    """The full NFL season, browsable by week or by team."""
    from web.nfl_schedule_view import build_context as schedule_context

    return render(request, "web/nfl_schedule.html",
                  schedule_context(request.GET, timezone.localdate()))
