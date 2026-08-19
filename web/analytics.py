"""Django-facing assembly for Results and Performance.

All outcome math remains in services.grading. This module only validates URL state,
applies shared filters, and prepares framework-neutral presentation context.
"""

from __future__ import annotations

from datetime import date, timedelta
from math import ceil
from urllib.parse import urlencode

from components.results_feed import (
    calibration_interpretation,
    calibration_table_html,
    cohort_comparison_html,
    consistency_html,
    daily_summary_html,
    edge_table_html,
    monthly_table_html,
    market_trend_matrix_html,
    over_under_html,
    period_comparison_html,
    period_summary_html,
    prop_list_html,
    version_table_html,
)
from domain import markets
from domain.markets import LABELS, ORDER, prop_type_for
from services import base_rates, grading

PERIODS = [
    ("7", "7 days"),
    ("30", "30 days"),
    ("90", "90 days"),
    ("season", "Season"),
    ("all", "All time"),
]
MIN_SAMPLES = (10, 30, 50)
RESULT_ORDER = {"hit": 0, "miss": 1, "void": 2, None: 3, "pending": 3}
PERFORMANCE_EXCLUDED_MARKETS = {"batter_tb", "batter_bb"}
PERFORMANCE_EXCLUDED_TYPES = {"tb", "batter_bb"}


def query_url(path: str, params, **updates) -> str:
    values = {key: value for key, value in params.items() if value not in (None, "", "all")}
    for key, value in updates.items():
        if value in (None, "", "all"):
            values.pop(key, None)
        else:
            values[key] = value
    encoded = urlencode(values)
    return f"{path}?{encoded}" if encoded else path


def _active(params, *, include_band: bool = True) -> dict[str, str]:
    keys = ("league", "market", "direction", "result")
    active = {key: params.get(key, "all") for key in keys}
    if include_band:
        active["band"] = params.get("band", "all")
    return active


def _direction(row: dict) -> str:
    return row.get("direction") or markets.resolve(row.get("league"), row.get("market"))[1]


def _market_type(row: dict) -> str:
    return prop_type_for(
        row.get("market_key"), row.get("league"), row.get("market")
    )


def apply_filters(rows: list[dict], active: dict[str, str]) -> list[dict]:
    out = rows
    if active.get("league", "all") != "all":
        out = [row for row in out if row.get("league") == active["league"]]
    if active.get("market", "all") != "all":
        out = [row for row in out if _market_type(row) == active["market"]]
    if active.get("direction", "all") != "all":
        out = [row for row in out if _direction(row) == active["direction"]]
    if active.get("result", "all") != "all":
        out = [
            row
            for row in out
            if (row.get("result") or "pending") == active["result"]
        ]
    band = active.get("band", "all")
    if band != "all":
        try:
            low, high = (int(value) for value in band.split("-", 1))
        except (TypeError, ValueError):
            pass
        else:
            out = [
                row
                for row in out
                if low <= (row.get("opportunity_score") or -1) <= high
            ]
    return out


def load_performance_range(start: date, end: date) -> list[dict]:
    return [
        row for row in grading.load_graded_range(start, end)
        if row.get("market_key") not in PERFORMANCE_EXCLUDED_MARKETS
        and _market_type(row) not in PERFORMANCE_EXCLUDED_TYPES
    ]


def apply_cohort(rows: list[dict], cohort: str) -> list[dict]:
    """Public cohorts: every 70+ prediction, Today's eight, or the remainder."""
    qualifying = grading.qualifying(rows)
    if cohort == "featured":
        return [row for row in qualifying if row.get("featured")]
    if cohort == "other":
        return [row for row in qualifying if not row.get("featured")]
    return qualifying


def filter_groups(path: str, params, active: dict[str, str], *, include_band: bool = True,
                  market_keys=None):
    market_keys = list(market_keys if market_keys is not None else ORDER)
    specs = [
        ("league", "League", [("all", "All"), ("MLB", "MLB"), ("WNBA", "WNBA")]),
        ("market", "Market", [("all", "All")] + [(key, LABELS[key]) for key in market_keys]),
        ("direction", "Direction", [("all", "All"), ("over", "Over"), ("under", "Under")]),
        ("result", "Result", [("all", "All"), ("hit", "Hit"), ("miss", "Miss"),
                                  ("void", "Void"), ("pending", "Pending")]),
    ]


def performance_url(params, **updates) -> str:
    """Bound the public Performance state to combinations we can publish statically."""
    values = {
        key: params.get(key)
        for key in ("period", "cohort", "market", "direction")
        if params.get(key) not in (None, "", "all")
    }
    values.update(updates)
    return query_url("/performance/", values)


def performance_filter_groups(params, active: dict[str, str], market_keys: list[str]):
    by_league = {"MLB": [], "WNBA": []}
    for key in market_keys:
        leagues = {
            spec.league for spec in markets.MARKETS.values()
            if spec.prop_type == key
        }
        for league in by_league:
            if league in leagues:
                by_league[league].append(key)

    groups = [{
        "key": "market", "label": "Market",
        "options": [{
            "value": "all", "label": "All",
            "active": active.get("market", "all") == "all",
            "href": performance_url(params, market="all"),
        }],
    }]
    for league in ("MLB", "WNBA"):
        category_label = "⚾" if league == "MLB" else "🏀"
        groups.append({
            "key": f"market-{league.lower()}", "label": category_label,
            "accessible_label": "Baseball markets" if league == "MLB" else "Basketball markets",
            "options": [
                {"value": key, "label": LABELS[key],
                 "active": active.get("market") == key,
                 "href": performance_url(params, market=key)}
                for key in by_league[league]
            ],
        })
    groups.append({
        "key": "direction", "label": "Direction",
        "options": [
            {"value": value, "label": label,
             "active": active.get("direction", "all") == value,
             "href": performance_url(params, direction=value)}
            for value, label in (("all", "All"), ("over", "Over"), ("under", "Under"))
        ],
    })
    return groups
    if include_band:
        specs.insert(
            2,
            ("band", "Score", [("all", "All")] + [
                (f"{low}-{high}", label) for low, high, label in grading.SCORE_BANDS
            ]),
        )
    return [
        {
            "key": key,
            "label": label,
            "options": [
                {
                    "value": value,
                    "label": display,
                    "active": active.get(key, "all") == value,
                    "href": query_url(path, params, **{key: value}),
                }
                for value, display in options
            ],
        }
        for key, label, options in specs
    ]


def parse_results_date(raw: str | None, today: date) -> date:
    latest = today - timedelta(days=1)
    try:
        selected = date.fromisoformat(raw) if raw else latest
    except ValueError:
        selected = latest
    return min(selected, latest)


def results_context(params, today: date) -> dict:
    selected_date = parse_results_date(params.get("date"), today)
    snapshot_rows = grading.load_graded_slate(selected_date)
    rows = grading.qualifying(snapshot_rows)
    active = _active(params)
    filtered = apply_filters(rows, active)
    query = (params.get("q") or "").strip().lower()
    if query:
        filtered = [
            row for row in filtered
            if any(query in str(row.get(key) or "").lower()
                   for key in ("player_name", "team_name", "opponent"))
        ]
    sort = params.get("sort", "score-desc")
    sorters = {
        "score-desc": lambda row: -(row.get("opportunity_score") or 0),
        "score-asc": lambda row: row.get("opportunity_score") or 0,
        "player": lambda row: str(row.get("player_name") or "").lower(),
        "result": lambda row: RESULT_ORDER.get(row.get("result"), 3),
    }
    if sort not in sorters:
        sort = "score-desc"
    filtered = sorted(filtered, key=sorters[sort])
    total_filtered = len(filtered)
    per_page = 10_000
    total_pages = max(1, ceil(total_filtered / per_page))
    try:
        page = int(params.get("page", "1"))
    except ValueError:
        page = 1
    page = min(max(page, 1), total_pages)
    page_rows = filtered[(page - 1) * per_page:page * per_page]
    overall = grading.tally(filtered)
    scores = [row["opportunity_score"] for row in filtered if row.get("opportunity_score") is not None]
    by_market = grading.summarize_by_market(filtered)
    return {
        "section": "results",
        "selected_date": selected_date,
        "latest_date": today - timedelta(days=1),
        "previous_href": query_url("/results/", params, date=(selected_date - timedelta(days=1)).isoformat()),
        "next_href": query_url("/results/", params, date=(selected_date + timedelta(days=1)).isoformat()),
        "can_go_next": selected_date < today - timedelta(days=1),
        "recent_dates": [_result_date_option(today - timedelta(days=offset), selected_date)
                         for offset in range(1, 8)],
        "filter_groups": [],
        "active_filters": [
            {"key": key, "value": value}
            for key, value in active.items() if value != "all"
        ],
        "summary_html": daily_summary_html(
            overall, sum(scores) / len(scores) if scores else None, len(filtered)
        ) if rows else "",
        "market_rows": [
            {"key": key, "label": LABELS.get(key, key), **tally,
             "decided": tally["hit"] + tally["miss"],
             "hit_rate_display": (
                 f"{tally['hit_rate']:.1%}" if tally["hit_rate"] is not None else "—"
             )}
            for key, tally in by_market.items()
        ],
        "prop_html": prop_list_html(page_rows) if rows else "",
        "prop_count": total_filtered,
        "visible_start": ((page - 1) * per_page + 1) if total_filtered else 0,
        "visible_end": min(page * per_page, total_filtered),
        "page": page,
        "total_pages": total_pages,
        "page_previous": query_url("/results/", params, page=page - 1) if page > 1 else None,
        "page_next": query_url("/results/", params, page=page + 1) if page < total_pages else None,
        "has_rows": bool(rows),
        "has_snapshot": bool(snapshot_rows),
        "query_text": params.get("q", ""),
        "sort": sort,
    }


def period_range(period: str, today: date) -> tuple[date, date, str]:
    end = today - timedelta(days=1)
    if period == "7":
        return end - timedelta(days=6), end, "Last 7 days"
    if period == "90":
        return end - timedelta(days=89), end, "Last 90 days"
    if period == "season":
        return date(end.year, 3, 1), end, f"{end.year} season"
    if period == "all":
        return date(2020, 1, 1), end, "All time"
    return end - timedelta(days=29), end, "Last 30 days"


def _result_date_option(day: date, selected: date) -> dict:
    rows = grading.load_graded_slate(day)
    qualifying = grading.qualifying(rows)
    tally = grading.tally(qualifying)
    if not rows:
        state, state_label = "missing", "No snapshot"
    elif not qualifying:
        state, state_label = "none", "No 70+"
    elif tally["pending"] and not (tally["hit"] or tally["miss"] or tally["void"]):
        state, state_label = "pending", "Pending"
    else:
        state, state_label = "graded", "Graded"
    return {"date": day, "active": selected == day,
            "href": query_url("/results/", {}, date=day.isoformat()),
            "state": state, "state_label": state_label}


def _version_groups(rows: list[dict]) -> list[dict]:
    """Model versions grouped by **market family**, not listed one per version.

    Fourteen version rows is a wall, and a flat "old models" roll-up is worse: it would
    average `batter_tb` — a market **retired** for converting 21% and never clearing the
    curation floor — together with `batter_hit`, an engine that simply got better. Those
    are different facts, and merging them makes every superseded scorer look worse than it
    was while flattering the current one.

    So: one group per market family, its live version expanded, everything earlier
    collapsed behind a count, and retired markets in a section of their own.
    """
    from domain.markets import LABELS, MARKETS
    from services.snapshots import MODEL_VERSIONS

    families: dict[str, dict] = {}
    for row in rows:
        key = row.get("market_key") or "unknown"
        version = row.get("scoring_engine_version") or "unversioned"
        fam = families.setdefault(key, {})
        entry = fam.setdefault(version, {"rows": [], "first": None, "last": None})
        entry["rows"].append(row)
        day = row.get("snapshot_date")
        if day:
            entry["first"] = min(entry["first"] or day, day)
            entry["last"] = max(entry["last"] or day, day)

    groups: list[dict] = []
    for key, by_version in families.items():
        spec = MARKETS.get(key)
        live = MODEL_VERSIONS.get(key)
        # `LABELS` is keyed by prop type and already disambiguates markets that share a
        # noun — batter and SP strikeouts are both "Strikeouts" in `spec.noun`, which
        # rendered two identical group headings. The filter pills use the same source,
        # so the names match what a reader has already seen.
        label = LABELS.get(spec.prop_type, spec.noun) if spec else key
        if spec:
            label = f"{spec.league} {label}" if not label.startswith(spec.league) else label
        current, earlier = None, []
        for version, entry in by_version.items():
            # Each version against the base rate of the props *it* served. Versions move
            # thresholds, so two versions of one market can face different base rates;
            # comparing both to the app-wide average would read that as a quality change.
            item = {"version": version, "tally": grading.tally(entry["rows"]),
                    "base": base_rates.segment_base_rate(entry["rows"]),
                    "first": entry["first"] or "—", "last": entry["last"] or "—"}
            # A retired market has no *current* version even though MODEL_VERSIONS still
            # names one — the spec is kept only so old ledger rows resolve.
            if version == live and not (spec and spec.retired):
                current = item
            else:
                earlier.append(item)
        earlier.sort(key=lambda i: i["last"], reverse=True)
        pooled = grading.tally([r for v in by_version.values() for r in v["rows"]])
        groups.append({
            "key": key, "label": label,
            "retired": spec.retired if spec else "",
            "current": current, "earlier": earlier, "pooled": pooled,
            "earlier_tally": grading.tally(
                [r for v, e in by_version.items() for r in e["rows"]
                 if not (v == live and not (spec and spec.retired))]),
            "earlier_base": base_rates.segment_base_rate(
                [r for v, e in by_version.items() for r in e["rows"]
                 if not (v == live and not (spec and spec.retired))]),
        })
    # Live markets first, ordered by sample; retired markets last.
    groups.sort(key=lambda g: (bool(g["retired"]),
                               -(g["pooled"]["hit"] + g["pooled"]["miss"])))
    return groups


def performance_context(params, today: date) -> dict:
    period = params.get("period", "30")
    if period not in {key for key, _ in PERIODS}:
        period = "30"
    min_sample = 30
    cohort = params.get("cohort", "qualifying")
    if cohort not in {"qualifying", "featured", "other"}:
        cohort = "qualifying"
    start, end, label = period_range(period, today)
    active = _active(params, include_band=False)
    performance_markets = [key for key in ORDER if key not in PERFORMANCE_EXCLUDED_TYPES]
    eligible_rows = load_performance_range(start, end)
    filtered_eligible = apply_filters(eligible_rows, active)
    rows = apply_cohort(filtered_eligible, cohort)
    if not rows:
        return {
            "section": "performance", "has_rows": False, "period": period,
            "min_sample": min_sample, "period_label": label, "cohort": cohort,
            "cohort_options": _cohort_options(params, cohort),
            "period_options": _period_options(params, period),
            "filter_groups": performance_filter_groups(params, active, performance_markets),
        }

    overall = grading.tally(rows)
    scores = [row["opportunity_score"] for row in rows if row.get("opportunity_score") is not None]
    slates = len({row.get("snapshot_date") for row in rows if row.get("snapshot_date")})
    qualifying_rows = apply_cohort(filtered_eligible, "qualifying")
    featured_rows = apply_cohort(filtered_eligible, "featured")
    other_rows = apply_cohort(filtered_eligible, "other")
    span = (end - start).days + 1
    prior_rows = apply_filters(apply_cohort(
        load_performance_range(start - timedelta(days=span), start - timedelta(days=1)), cohort
    ), active)
    prior = grading.tally(prior_rows)
    bands = grading.summarize_by_band(rows, min_sample=min_sample)
    # Bands hold different market mixes (the top band is almost purely 1+ hit), so each
    # is compared against the base rate of the props it actually contains.
    band_rows: dict = {}
    for row in rows:
        b = grading.band_of(row.get("opportunity_score"))
        if b:
            band_rows.setdefault(b, []).append(row)
    band_base = {b: base_rates.segment_base_rate(rs) for b, rs in band_rows.items()}
    empty = grading.tally([])
    directions = grading.summarize_by(rows, _direction)
    market_ou = []
    for key in performance_markets:
        subset = [row for row in rows if _market_type(row) == key]
        if subset:
            summary = grading.summarize_by(subset, _direction)
            market_ou.append((LABELS[key], summary.get("over", empty), summary.get("under", empty)))

    grouping = params.get("group", "market")
    groupings = {
        "market": ("Market", lambda row: LABELS.get(_market_type(row), _market_type(row))),
        "league": ("League", lambda row: row.get("league")),
        "direction": ("Direction", lambda row: _direction(row).title()),
        "band": ("Score band", lambda row: grading.band_of(row.get("opportunity_score"))),
        "team": ("Team", lambda row: row.get("team_name")),
        "player": ("Player", lambda row: row.get("player_name")),
    }
    if grouping not in groupings:
        grouping = "market"
    by_segment = grading.summarize_by(rows, groupings[grouping][1])
    recent = {key: tally["hit_rate"] for key, tally in by_segment.items()}
    # Each segment against *its own* base rate, not the app-wide average. A segment can
    # mix markets and bars (grouping by team or player does), so it is weighted by the
    # exact props it contains. See services/base_rates for why the shared average is the
    # wrong comparison.
    seg_rows: dict = {}
    for row in rows:
        seg = groupings[grouping][1](row)
        if seg not in (None, ""):
            seg_rows.setdefault(seg, []).append(row)
    seg_base = {seg: base_rates.segment_base_rate(rs) for seg, rs in seg_rows.items()}

    def window(days: int, offset: int = 0):
        window_end = end - timedelta(days=offset)
        window_start = window_end - timedelta(days=days - 1)
        return grading.tally(apply_filters(
            apply_cohort(load_performance_range(window_start, window_end), cohort), active))

    all_rows = apply_filters(apply_cohort(
        load_performance_range(date(2020, 1, 1), end), cohort), active)
    all_rate = grading.tally(all_rows)["hit_rate"]
    def _month_of(row):
        return (row.get("snapshot_date") or "")[:7] or None
    months = sorted(grading.summarize_by(all_rows, _month_of).items())
    month_rows: dict = {}
    for row in all_rows:
        m = _month_of(row)
        if m:
            month_rows.setdefault(m, []).append(row)
    month_base = {m: base_rates.segment_base_rate(rs) for m, rs in month_rows.items()}
    version_items = _version_groups(all_rows)
    return {
        "section": "performance", "has_rows": True, "period": period,
        "min_sample": min_sample, "period_label": label, "cohort": cohort,
        "cohort_options": _cohort_options(params, cohort),
        "period_options": _period_options(params, period),
        "filter_groups": performance_filter_groups(params, active, performance_markets),
        "summary_html": period_summary_html(
            overall, sum(scores) / len(scores) if scores else None, label,
            cohort={"qualifying": "All qualifying", "featured": "Featured",
                    "other": "Other qualifying"}[cohort], slates=slates,
        ),
        "cohort_comparison_html": cohort_comparison_html(
            grading.tally(qualifying_rows), grading.tally(featured_rows),
            grading.tally(other_rows)),
        "market_trend_html": market_trend_matrix_html(rows),
        "comparison_html": period_comparison_html(overall, prior, f"previous {label.lower()}", min_sample),
        "calibration_read": calibration_interpretation(bands, band_base),
        "calibration_html": calibration_table_html(bands, overall["hit_rate"], band_base),
        "over_under_html": over_under_html(
            directions.get("over", empty), directions.get("under", empty), market_ou
        ),
        "edge_html": edge_table_html(by_segment, overall["hit_rate"], min_sample, recent, {},
                                     seg_base=seg_base),
        "consistency_html": consistency_html([
            ("Last 7", window(7)), ("Last 30", window(30)),
            ("Prev 30", window(30, 30)),
            ("Season", grading.tally(apply_filters(
                apply_cohort(load_performance_range(date(end.year, 3, 1), end), cohort), active))),
            ("All time", grading.tally(all_rows)),
        ]),
        "monthly_html": monthly_table_html(months, all_rate, month_base),
        "version_html": version_table_html(version_items, all_rate),
    }


def _period_options(params, current):
    return [{"key": key, "label": label, "active": key == current,
             "href": performance_url(params, period=key)} for key, label in PERIODS]


def _cohort_options(params, current):
    return [
        {"key": key, "label": label, "active": key == current,
         "href": performance_url(params, cohort=key)}
        for key, label in (("qualifying", "All qualifying"),
                           ("featured", "Featured"),
                           ("other", "Other qualifying"))
    ]


def _sample_options(params, current):
    return [{"value": value, "label": f"{value}+", "active": value == current,
             "href": query_url("/performance/", params, min=value)} for value in MIN_SAMPLES]
