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
    consistency_html,
    daily_summary_html,
    edge_table_html,
    monthly_table_html,
    over_under_html,
    period_comparison_html,
    period_summary_html,
    prop_list_html,
    version_table_html,
)
from domain import markets
from domain.markets import LABELS, ORDER, prop_type_for
from services import grading

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
    rows = grading.load_graded_slate(selected_date)
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
    per_page = 100
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
        "filter_groups": filter_groups("/results/", params, active),
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


def performance_context(params, today: date) -> dict:
    period = params.get("period", "30")
    if period not in {key for key, _ in PERIODS}:
        period = "30"
    try:
        min_sample = int(params.get("min", "30"))
    except ValueError:
        min_sample = 30
    if min_sample not in MIN_SAMPLES:
        min_sample = 30
    start, end, label = period_range(period, today)
    active = _active(params, include_band=False)
    performance_markets = [key for key in ORDER if key not in PERFORMANCE_EXCLUDED_TYPES]
    eligible_rows = load_performance_range(start, end)
    rows = apply_filters(eligible_rows, active)
    if not rows:
        return {
            "section": "performance", "has_rows": False, "period": period,
            "min_sample": min_sample, "period_label": label,
            "period_options": _period_options(params, period),
            "sample_options": _sample_options(params, min_sample),
            "filter_groups": filter_groups(
                "/performance/", params, active, include_band=False,
                market_keys=performance_markets,
            ),
        }

    overall = grading.tally(rows)
    served = grading.tally(grading.split_served(rows)[0])
    scores = [row["opportunity_score"] for row in rows if row.get("opportunity_score") is not None]
    span = (end - start).days + 1
    prior_rows = apply_filters(
        load_performance_range(start - timedelta(days=span), start - timedelta(days=1)), active
    )
    prior = grading.tally(prior_rows)
    bands = grading.summarize_by_band(rows, min_sample=min_sample)
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

    def window(days: int, offset: int = 0):
        window_end = end - timedelta(days=offset)
        window_start = window_end - timedelta(days=days - 1)
        return grading.tally(apply_filters(load_performance_range(window_start, window_end), active))

    all_rows = apply_filters(load_performance_range(date(2020, 1, 1), end), active)
    all_rate = grading.tally(all_rows)["hit_rate"]
    months = sorted(grading.summarize_by(
        all_rows, lambda row: (row.get("snapshot_date") or "")[:7] or None
    ).items())
    versions: dict[str, list[dict]] = {}
    version_dates: dict[str, tuple[str, str]] = {}
    for row in all_rows:
        version = row.get("scoring_engine_version") or "unversioned"
        versions.setdefault(version, []).append(row)
        token = row.get("snapshot_date")
        if token:
            low, high = version_dates.get(version, (token, token))
            version_dates[version] = (min(low, token), max(high, token))
    version_items = sorted(
        ((version, grading.tally(version_rows), *version_dates.get(version, ("—", "—")))
         for version, version_rows in versions.items()),
        key=lambda item: item[3],
    )
    return {
        "section": "performance", "has_rows": True, "period": period,
        "min_sample": min_sample, "period_label": label,
        "period_options": _period_options(params, period),
        "sample_options": _sample_options(params, min_sample),
        "group_options": [
            {"key": key, "label": value[0], "active": key == grouping,
             "href": query_url("/performance/", params, group=key)}
            for key, value in groupings.items()
        ],
        "filter_groups": filter_groups(
            "/performance/", params, active, include_band=False,
            market_keys=performance_markets,
        ),
        "summary_html": period_summary_html(
            overall, sum(scores) / len(scores) if scores else None, label,
            served=served, floor=grading.CURATION_FLOOR,
        ),
        "comparison_html": period_comparison_html(overall, prior, f"previous {label.lower()}", min_sample),
        "calibration_read": calibration_interpretation(bands),
        "calibration_html": calibration_table_html(bands, overall["hit_rate"]),
        "over_under_html": over_under_html(
            directions.get("over", empty), directions.get("under", empty), market_ou
        ),
        "edge_html": edge_table_html(by_segment, overall["hit_rate"], min_sample, recent, {}),
        "consistency_html": consistency_html([
            ("Last 7", window(7)), ("Last 30", window(30)),
            ("Prev 30", window(30, 30)),
            ("Season", grading.tally(apply_filters(
                load_performance_range(date(end.year, 3, 1), end), active))),
            ("All time", grading.tally(all_rows)),
        ]),
        "monthly_html": monthly_table_html(months, all_rate),
        "version_html": version_table_html(version_items, all_rate),
    }


def _period_options(params, current):
    return [{"key": key, "label": label, "active": key == current,
             "href": query_url("/performance/", params, period=key)} for key, label in PERIODS]


def _sample_options(params, current):
    return [{"value": value, "label": f"{value}+", "active": value == current,
             "href": query_url("/performance/", params, min=value)} for value in MIN_SAMPLES]
