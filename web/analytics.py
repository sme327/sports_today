"""Django-facing assembly for Results and Performance.

All outcome math remains in services.grading. This module only validates URL state,
applies shared filters, and prepares framework-neutral presentation context.
"""

from __future__ import annotations

from datetime import date, timedelta
from math import ceil
from urllib.parse import urlencode

from components.results_feed import (
    calibration_bars_html,
    calibration_interpretation,
    calibration_table_html,
    cohort_comparison_html,
    confident_misses_html,
    consistency_html,
    daily_read_html,
    daily_summary_html,
    edge_table_html,
    hit_rate_context_html,
    is_starved,
    market_coverage_html,
    market_table_html,
    market_trend_matrix_html,
    monthly_table_html,
    over_under_html,
    performance_summary_html,
    period_comparison_html,
    prop_list_html,
    signal_check_html,
    trust_board_html,
    version_table_html,
)
from domain import markets
from domain.markets import LABELS, ORDER, prop_type_for
from services import base_rates, grading, model_trust

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
    # Baseball splits by *who the prop is about*, not just by league. Four MLB markets in
    # one row crowd a phone, and "Batter Hits, Batter Ks" and "SP Strikeouts, SP Hits
    # Allowed" are the two groups a reader already thinks in — they answer different
    # questions and are never compared to each other.
    def _pills(keys):
        return [{"value": key, "label": LABELS[key],
                 "active": active.get("market") == key,
                 "href": performance_url(params, market=key)}
                for key in keys]

    mlb = by_league["MLB"]
    batters = [k for k in mlb if not k.startswith("sp_")]
    pitchers = [k for k in mlb if k.startswith("sp_")]
    for key, label, accessible, keys in (
        ("market-mlb-batter", "⚾ Batter", "Baseball batter markets", batters),
        ("market-mlb-sp", "⚾ Pitcher", "Baseball starting-pitcher markets", pitchers),
        ("market-wnba", "🏀", "Basketball markets", by_league["WNBA"]),
    ):
        if keys:
            groups.append({"key": key, "label": label, "accessible_label": accessible,
                           "options": _pills(keys)})
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


# --- Daily Results: the day against normal ------------------------------------------
# The trailing window a day is judged against. Thirty days is the Performance page's own
# default period, and the population is the same one that page reports on, so "the 30-day
# average" means the same number on both surfaces rather than two numbers that nearly
# agree.
RESULTS_TREND_DAYS = 30
RESULTS_MIN_PRIOR = 30      # graded props before a trailing window is worth comparing to
RESULTS_MIN_DAY = 20        # graded props before the day itself is worth reading
RESULTS_MARKET_SAMPLE = 5   # decided props before a market's lift is quoted
RESULTS_READ_MARKET = 10    # ...and before the daily read calls it the day's story
RESULTS_TOP_N = 10          # "the predictions we were most sure about"


def decided_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("result") in ("hit", "miss")]


def lift_over_base(rows: list[dict]) -> float | None:
    """Hit rate minus the base rate of the exact props decided — never a raw hit rate.

    Judged on decided rows only, so the comparison shares the hit rate's denominator: a
    void is not a prop that landed, and it is not a prop that was available to land.
    """
    dec = decided_rows(rows)
    if not dec:
        return None
    base = base_rates.segment_base_rate(dec)
    if base is None:
        return None
    return sum(row.get("result") == "hit" for row in dec) / len(dec) - base


def trailing_rows(selected_date: date, days: int = RESULTS_TREND_DAYS) -> list[dict]:
    """The qualifying predictions of the ``days`` days **before** the selected date.

    The day being judged is excluded on purpose: a slate that is 8% of its own comparison
    window pulls the average toward itself, which flatters a good day and cushions a bad
    one. For an older date the window is the days before *that* date, so a result read a
    week later says what it said on the morning after.
    """
    end = selected_date - timedelta(days=1)
    return apply_cohort(load_performance_range(end - timedelta(days=days - 1), end),
                        "qualifying")


def _market_rows(rows: list[dict]) -> list[dict]:
    """Per-market record, hit rate, lift over base and average score, biggest first.

    Ordered by how many predictions were decided, because on a daily slate that is the
    market that made the day — a 2–0 market at the top of a lift ranking says nothing
    about how the afternoon went. (Performance ranks by lift; it is reading months.)
    """
    by_market = grading.summarize_by_market(rows)
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(_market_type(row), []).append(row)
    out = []
    for key, tally in by_market.items():
        subset = grouped.get(key, [])
        scores = [row["opportunity_score"] for row in subset
                  if row.get("opportunity_score") is not None]
        out.append({
            "key": key, "label": LABELS.get(key, key), **tally,
            "decided": tally["hit"] + tally["miss"],
            "lift": lift_over_base(subset),
            "avg_score": (sum(scores) / len(scores)) if scores else None,
            "hit_rate_display": (
                f"{tally['hit_rate']:.1%}" if tally["hit_rate"] is not None else "—"),
        })
    out.sort(key=lambda item: (-item["decided"], item["label"]))
    return out


def _confident_misses(rows: list[dict], top_n: int = RESULTS_TOP_N,
                      show: int = 3) -> tuple[list[dict], int, dict]:
    """Misses among the day's ``top_n`` highest-scored predictions.

    Not the largest numerical gaps: a strikeout line missed by five is a more dramatic
    row than a 93-scored 1+ hit that went 0-for-4, and only the second one says anything
    about whether the top of the scale means what it claims. Voids are not misses and
    are excluded from the sample entirely — a scratch is not a wrong call.
    """
    ranked = sorted((row for row in decided_rows(rows)),
                    key=lambda row: -(row.get("opportunity_score") or 0))[:top_n]
    if len(ranked) < top_n:
        return [], 0, grading.tally([])
    missed = [row for row in ranked if row.get("result") == "miss"]
    out = []
    for row in missed[:show]:
        key = row.get("market_key") or markets.resolve(row.get("league"), row.get("market"))[0]
        out.append({
            **row,
            "market_label": LABELS.get(
                _market_type(row), str(row.get("market") or "")),
            "recommendation": (markets.recommendation_label(
                key, row.get("threshold"), row.get("direction")) if key else ""),
            "actual": markets.actual_display(key, row["actual_value"])
            if row.get("actual_value") is not None else "—",
        })
    return out, len(missed), grading.tally(ranked)


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
    market_rows = _market_rows(filtered)
    misses, missed_count, top_tally = _confident_misses(filtered)

    # The day against the thirty before it, on both scales: the hit rate a reader asks
    # for, and the lift over base the project actually judges on. Computed here so the
    # comparison line and the daily read narrate the same figures.
    prior = trailing_rows(selected_date)
    prior_tally = grading.tally(prior)
    prior_decided = decided_rows(prior)
    day_decided = decided_rows(filtered)
    comparison = {
        "days": RESULTS_TREND_DAYS,
        "day_rate": overall["hit_rate"], "day_decided": len(day_decided),
        "prior_rate": prior_tally["hit_rate"], "prior_decided": len(prior_decided),
        "day_lift": lift_over_base(filtered), "prior_lift": lift_over_base(prior),
        "day_base": base_rates.segment_base_rate(day_decided),
        "prior_base": base_rates.segment_base_rate(prior_decided),
    }
    read = {
        **comparison,
        "markets": market_rows,
        "top_n": RESULTS_TOP_N, "top_missed": missed_count,
        "top_hit": top_tally["hit"], "top_rate": top_tally["hit_rate"],
        "min_day": RESULTS_MIN_DAY, "min_prior": RESULTS_MIN_PRIOR,
        "min_market": RESULTS_MARKET_SAMPLE, "read_market": RESULTS_READ_MARKET,
    }
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
        "comparison_html": hit_rate_context_html(
            comparison, min_prior=RESULTS_MIN_PRIOR) if rows else "",
        "daily_read_html": daily_read_html(read) if rows else "",
        "market_html": market_table_html(
            market_rows, min_lift_sample=RESULTS_MARKET_SAMPLE) if rows else "",
        "market_rows": market_rows,
        "misses_html": confident_misses_html(misses, RESULTS_TOP_N, missed_count),
        "market_filters": [{"key": item["key"], "label": item["label"],
                            "count": item["total"]} for item in market_rows],
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
        # "Did the new model actually improve?" — against the version it *replaced*, not
        # against every earlier version pooled. Pooling would compare batter-hit-v6 with
        # an average that includes mlb-1hit-v0.1, which flatters it for a fix made three
        # versions ago. Measured in lift, because versions move thresholds and so face
        # different base rates; a raw-rate comparison would read that as a quality change.
        previous = earlier[0] if earlier else None
        change = previous_version = comparison_note = None
        comparison_small = False
        if current and previous:
            previous_version = previous["version"]
            cur_lift = (None if current["tally"]["hit_rate"] is None or current["base"] is None
                        else current["tally"]["hit_rate"] - current["base"])
            prev_lift = (None if previous["tally"]["hit_rate"] is None or previous["base"] is None
                         else previous["tally"]["hit_rate"] - previous["base"])
            if cur_lift is None or prev_lift is None:
                comparison_note = f"no base rate for {previous_version}"
            else:
                change = cur_lift - prev_lift
                comparison_small = min(
                    grading.decided(current["tally"]), grading.decided(previous["tally"])
                ) < grading.MIN_SAMPLE
        elif current:
            comparison_note = "first version on this ledger"
        groups.append({
            "key": key, "label": label,
            "retired": spec.retired if spec else "",
            "current": current, "earlier": earlier, "pooled": pooled,
            "previous_version": previous_version, "change_vs_previous": change,
            "comparison_small": comparison_small, "comparison_note": comparison_note,
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
            "active_filter_chips": _active_filter_chips(params, active, cohort, label),
        }

    # period_range's label is meant for a section headline ("Last 30 days"), so used
    # verbatim after "previous" it reads "previous last 30 days" — strip the leading
    # "last" only for this phrasing.
    label_lower = label.lower()
    prior_label = f"previous {label_lower[5:] if label_lower.startswith('last ') else label_lower}"
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
    # Calibration reads the **current** engine only. Pooled across versions, the 99-100
    # band showed −6.6 over base and looked anti-predictive; split by engine it is −1.7
    # all-time and +13.4 for batter-hit-v5 alone. A ledger mixes engines exactly as a
    # blended average mixes markets, and a superseded scorer's calibration is not a fact
    # about the one running today. Per-version records stay in the model table below.
    from services.snapshots import MODEL_VERSIONS

    def _is_current(row: dict) -> bool:
        key = row.get("market_key")
        live = MODEL_VERSIONS.get(key) if key else None
        return live is None or row.get("scoring_engine_version") == live

    current_rows = [row for row in rows if _is_current(row)]
    superseded = len(rows) - len(current_rows)
    band_rows = current_rows or rows
    bands = grading.summarize_by_band(band_rows, min_sample=min_sample)
    # Bands hold different market mixes (the top band is almost purely 1+ hit), so each
    # is compared against the base rate of the props it actually contains.
    band_row_groups: dict = {}
    for row in band_rows:
        b = grading.band_of(row.get("opportunity_score"))
        if b:
            band_row_groups.setdefault(b, []).append(row)
    band_base = {b: base_rates.segment_base_rate(rs) for b, rs in band_row_groups.items()}
    empty = grading.tally([])
    directions = grading.summarize_by(rows, _direction)
    # Lift over each side's own base rate, for the takeaway's over/under clause — a raw
    # hit-rate comparison would be misleading here for the same reason bands need their
    # own base rate: Over and Under don't share a base event rate across the market mix.
    direction_row_groups: dict[str, list[dict]] = {}
    for row in rows:
        d = _direction(row)
        if d:
            direction_row_groups.setdefault(d, []).append(row)
    direction_lift: dict[str, tuple[float, int]] = {}
    for d, rs in direction_row_groups.items():
        base = base_rates.segment_base_rate(rs)
        decided_d = [r for r in rs if r.get("result") in ("hit", "miss")]
        if base is None or not decided_d:
            continue
        hit_rate_d = sum(r.get("result") == "hit" for r in decided_d) / len(decided_d)
        direction_lift[d] = (hit_rate_d - base, len(decided_d))
    market_ou = []
    # …and the same split in lift, because the two sides of one market face different base
    # rates too: an SP-hits under clears ~53% on its own where the over clears ~47%. Two
    # raw hit rates side by side in this table read as a comparison and are not one.
    market_ou_lift: dict[tuple[str, str], float] = {}
    for key in performance_markets:
        subset = [row for row in rows if _market_type(row) == key]
        if subset:
            summary = grading.summarize_by(subset, _direction)
            market_ou.append((LABELS[key], summary.get("over", empty), summary.get("under", empty)))
            for side in ("over", "under"):
                side_rows = [r for r in subset
                             if _direction(r) == side and r.get("result") in ("hit", "miss")]
                base = base_rates.segment_base_rate(side_rows) if side_rows else None
                if base is not None:
                    market_ou_lift[(LABELS[key], side)] = (
                        sum(r.get("result") == "hit" for r in side_rows) / len(side_rows)
                        - base)

    # Coverage reads *everything recorded*, not the served cohort — that is the whole
    # point. A market whose scorer cannot reach the floor is invisible in every other
    # table on this page, and indistinguishable from one that simply does not work.
    decided = [r for r in filtered_eligible if r.get("result") in ("hit", "miss")]
    coverage = []
    for key in performance_markets:
        subset = [r for r in decided if _market_type(r) == key]
        if not subset:
            continue
        served = [r for r in subset
                  if (r.get("opportunity_score") or 0) >= grading.CURATION_FLOOR]

        def _lift(group):
            if not group:
                return None
            base = base_rates.segment_base_rate(group)
            if base is None:
                return None
            hit = sum(r.get("result") == "hit" for r in group) / len(group)
            return hit - base

        # Serving share is a property of the scorer running *today*, so the starvation
        # flag is judged on the current engine alone — the same split the calibration
        # bands above already make. Pooled, `batter-k-v1` (3.7% served) dragged the fixed
        # `batter-k-v2` (17.7%, +33.8 over base on what it serves) back under the flag's
        # own threshold, so the page advertised the exact problem the fix had closed.
        # The displayed columns stay pooled: that is the table's point.
        live = [r for r in subset if _is_current(r)]
        live_served = [r for r in live
                       if (r.get("opportunity_score") or 0) >= grading.CURATION_FLOOR]
        def _hit_rate(group):
            return (sum(r.get("result") == "hit" for r in group) / len(group)
                    if group else None)

        coverage.append({
            "key": key,
            "label": LABELS.get(key, key),
            "recorded_n": len(subset), "recorded_lift": _lift(subset),
            "recorded_hit_rate": _hit_rate(subset),
            "served_n": len(served), "served_lift": _lift(served),
            # The served hit rate and the base it is measured against, so "What's working"
            # can show conversion *and* the number that makes it meaningful in one row.
            "served_hit_rate": _hit_rate(served),
            "served_base": base_rates.segment_base_rate(served) if served else None,
            "live_n": len(live), "live_served_n": len(live_served), "live_lift": _lift(live),
        })
    # Ranked by served edge, but a market under the minimum sample never leads the table
    # however large its percentage: `batter_k` runs +41.8 on 22 graded props, and sorted on
    # the number alone it sat above a market with 1,403. That is the exact misreading this
    # page exists to prevent, so sample gates the ordering before lift does.
    coverage.sort(key=lambda c: ((c["served_n"] or 0) < min_sample,
                                 c["served_lift"] is None,
                                 -(c["served_lift"] or 0)))
    # `starved` is stamped here rather than recomputed downstream: the coverage table, the
    # signal check and the trust board must never disagree about whether a market's edge is
    # actually offered, and `is_starved` is the one definition of that.
    for item in coverage:
        item["starved"] = is_starved(item)

    # Each market's served lift in the previous period of the same length — the trust
    # board's "improving or cooling" input. Computed from `prior_rows`, which is already
    # loaded, so this costs nothing extra.
    prior_market_lift: dict[str, float] = {}
    for key in performance_markets:
        subset = [r for r in prior_rows
                  if _market_type(r) == key and r.get("result") in ("hit", "miss")]
        if len(subset) < min_sample:
            continue
        base = base_rates.segment_base_rate(subset)
        if base is None:
            continue
        prior_market_lift[LABELS.get(key, key)] = (
            sum(r.get("result") == "hit" for r in subset) / len(subset) - base)
    market_trend = {
        item["label"]: item["served_lift"] - prior_market_lift[item["label"]]
        for item in coverage
        if item["served_lift"] is not None and item["label"] in prior_market_lift
    }

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
    # The same segments in the previous period of equal length. The trend column used to
    # be handed an empty dict, so it printed today's rate labelled "30d" beside itself —
    # a column that answered "is this improving?" with the number it was asked about.
    prev = {seg: tally["hit_rate"]
            for seg, tally in grading.summarize_by(prior_rows, groupings[grouping][1]).items()
            if tally["hit"] + tally["miss"] >= min_sample}
    seg_n = {seg: len([r for r in rs if r.get("result") in ("hit", "miss")])
             for seg, rs in seg_rows.items()}

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

    # Overall lift is the page's second headline figure, so it is measured the same way
    # every other lift here is: against the base rate of the exact props in the selection,
    # not against a fixed 50% or a shared average. See services/base_rates.
    overall_lift = None
    if overall["hit_rate"] is not None:
        overall_base = base_rates.segment_base_rate(
            [r for r in rows if r.get("result") in ("hit", "miss")])
        if overall_base is not None:
            overall_lift = overall["hit_rate"] - overall_base
    else:
        overall_base = None
    prior_lift = None
    if prior["hit_rate"] is not None:
        prior_base = base_rates.segment_base_rate(
            [r for r in prior_rows if r.get("result") in ("hit", "miss")])
        if prior_base is not None:
            prior_lift = prior["hit_rate"] - prior_base

    consistency_windows = [
        {"label": "Last 7", "tally": window(7), "vs": "Last 30"},
        {"label": "Last 30", "tally": window(30), "vs": "Prev 30"},
        {"label": "Prev 30", "tally": window(30, 30), "vs": None},
        {"label": "Season", "tally": grading.tally(apply_filters(
            apply_cohort(load_performance_range(date(end.year, 3, 1), end), cohort),
            active)), "vs": None},
        {"label": "All time", "tally": grading.tally(all_rows), "vs": None},
    ]
    by_label = {w["label"]: w["tally"] for w in consistency_windows}
    for w in consistency_windows:
        target = by_label.get(w["vs"]) if w["vs"] else None
        w["delta"] = (
            w["tally"]["hit_rate"] - target["hit_rate"]
            if target is not None and target["hit_rate"] is not None
            and w["tally"]["hit_rate"] is not None
            and (target["hit"] + target["miss"]) >= min_sample
            else None)

    return {
        "section": "performance", "has_rows": True, "period": period,
        "min_sample": min_sample, "period_label": label, "cohort": cohort,
        "cohort_options": _cohort_options(params, cohort),
        "period_options": _period_options(params, period),
        "filter_groups": performance_filter_groups(params, active, performance_markets),
        "active_filter_chips": _active_filter_chips(params, active, cohort, label),

        # --- Level 1: conclusions before evidence ---------------------------------
        "signal_check_html": signal_check_html(model_trust.signal_check(
            coverage, overall, overall_lift, prior, prior_lift, prior_label, min_sample)),
        "summary_html": performance_summary_html(
            overall, overall_lift, prior, prior_lift, prior_label,
            avg_score=sum(scores) / len(scores) if scores else None, slates=slates,
            period_label=label, base_rate=overall_base,
            cohort={"qualifying": "All qualifying", "featured": "Featured",
                    "other": "Other qualifying"}[cohort],
        ),
        "what_this_means": model_trust.what_this_means(coverage, overall, overall_lift,
                                                       min_sample),
        "cohort_comparison_html": cohort_comparison_html(
            grading.tally(qualifying_rows), grading.tally(featured_rows),
            grading.tally(other_rows)),
        "market_coverage_html": market_coverage_html(coverage, grading.CURATION_FLOOR),
        "trust_board_html": trust_board_html(
            model_trust.trust_tiers(coverage, market_trend)),

        # --- Level 2: the primary evidence ----------------------------------------
        "calibration_reads": model_trust.calibration_conclusions(bands, band_base,
                                                                 overall_lift),
        "calibration_scope": (
            f"Current scoring engine only — {superseded:,} prediction"
            f"{'' if superseded == 1 else 's'} from superseded versions excluded. "
            f"Pooling engines once made the top band look anti-predictive when it "
            f"was not; per-version records are in the model table below."
        ) if superseded else "",
        "calibration_html": calibration_table_html(bands, overall["hit_rate"], band_base),
        "calibration_bars_html": calibration_bars_html(bands, band_base),
        "edge_html": edge_table_html(by_segment, overall["hit_rate"], min_sample, recent,
                                     prev, seg_base=seg_base),
        "edge_grouping": groupings[grouping][0],
        "over_under_html": over_under_html(
            directions.get("over", empty), directions.get("under", empty), market_ou,
            direction_lift=direction_lift, market_lift=market_ou_lift,
        ),
        "direction_read": model_trust.direction_conclusion(
            direction_lift.get("over"), direction_lift.get("under"), min_sample),

        # --- Level 3: the deep diagnostics ----------------------------------------
        "consistency_html": consistency_html(consistency_windows),
        "consistency_read": model_trust.consistency_conclusion(consistency_windows,
                                                               min_sample),
        "market_trend_html": market_trend_matrix_html(rows, base_of=base_rates.row_base_rate),
        "monthly_html": monthly_table_html(months, all_rate, month_base),
        "version_html": version_table_html(version_items, all_rate),
        "version_read": model_trust.version_summary(version_items),
    }


def _active_filter_chips(params, active: dict[str, str], cohort: str,
                         period_label: str) -> list[dict]:
    """The filters actually narrowing the page, each with a link that clears just itself.

    The pills above already show which option is selected; this answers the different
    question of *what am I looking at* — worth stating outright, because every figure
    below responds to it and a reader who has scrolled past the pills has no other way to
    tell a market-filtered page from the whole slate.
    """
    chips = []
    if cohort != "qualifying":
        chips.append({"label": "Cohort",
                      "value": {"featured": "Featured",
                                "other": "Other qualifying"}[cohort],
                      "clear": performance_url(params, cohort="qualifying")})
    if active.get("market", "all") != "all":
        chips.append({"label": "Market",
                      "value": LABELS.get(active["market"], active["market"]),
                      "clear": performance_url(params, market="all")})
    if active.get("direction", "all") != "all":
        chips.append({"label": "Direction", "value": active["direction"].title(),
                      "clear": performance_url(params, direction="all")})
    return chips


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
