from __future__ import annotations

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from web.today import build_context
from web.analytics import performance_context, results_context
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
