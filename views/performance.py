"""Performance view (R4): the longitudinal model-quality dashboard.

R4 delivers the highest-value section — Score calibration ("does a higher score
perform better?") — over a selectable period. Later phases add the time series,
edge finder, over/under, and trend sections. All tallies come from the centralized
grading helpers so this view can't diverge from Daily Results.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from components.filter_bar import active_filters, apply_filters, filter_bar_html
from components.results_feed import (calibration_interpretation, calibration_table_html,
                                     period_comparison_html, period_summary_html)
from router import NavState
from services import grading

# (key, label). Period back from yesterday (the latest gradeable day).
_PERIODS = [("7", "7 days"), ("30", "30 days"), ("90", "90 days"),
            ("season", "Season"), ("all", "All time")]
_MIN_SAMPLES = [10, 30, 50]


def _range(period: str) -> tuple[date, date, str]:
    end = date.today() - timedelta(days=1)
    if period == "7":
        return end - timedelta(days=6), end, "Last 7 days"
    if period == "90":
        return end - timedelta(days=89), end, "Last 90 days"
    if period == "season":
        return date(end.year, 3, 1), end, f"{end.year} season"
    if period == "all":
        return date(2020, 1, 1), end, "All time"
    return end - timedelta(days=29), end, "Last 30 days"   # default 30


def _pill_row(param: str, options, current, label: str) -> str:
    from components.filter_bar import filter_href
    pills = []
    for value, disp in options:
        active = " active" if str(value) == str(current) else ""
        pills.append(f'<a class="thr-pill{active}" target="_self" '
                     f'href="{filter_href(**{param: str(value)})}">{disp}</a>')
    return (f'<span class="thr-control"><span class="thr-label">{label}</span>'
            f'{"".join(pills)}</span>')


def render(nav: NavState) -> None:
    st.markdown('<a class="back-link" target="_self" href="?">← Back to today’s slate</a>',
                unsafe_allow_html=True)
    st.markdown(
        '<div class="section-row"><div class="page-title">Performance</div>'
        '<a class="results-link" target="_self" href="?view=results">Daily results →</a></div>',
        unsafe_allow_html=True)

    period = st.query_params.get("pd", "30")
    min_sample = int(st.query_params.get("min", "30")) if st.query_params.get("min", "30").isdigit() else 30
    start, end, period_label = _range(period)

    controls = (_pill_row("pd", _PERIODS, period, "Period")
                + '<span class="perf-ctl-gap"></span>'
                + _pill_row("min", [(m, f"{m}+") for m in _MIN_SAMPLES], min_sample, "Min sample"))
    st.markdown(f'<div class="perf-controls">{controls}</div>', unsafe_allow_html=True)

    # Shared filters (league / market / direction / result) — score band is the
    # calibration axis, so it isn't offered as a filter here.
    active = active_filters()
    active["bnd"] = "all"                      # never filter out bands on this view
    st.markdown(filter_bar_html(active, exclude=("bnd",)), unsafe_allow_html=True)
    rows = apply_filters(grading.load_graded_range(start, end), active)

    if not rows:
        st.markdown('<div class="mlb-empty">No graded props in this period yet. The '
                    'ledger fills in as you run the daily update.</div>', unsafe_allow_html=True)
        return

    overall = grading.summarize(rows)["overall"]
    scores = [r["opportunity_score"] for r in rows if r.get("opportunity_score") is not None]
    avg_score = sum(scores) / len(scores) if scores else None
    st.markdown(period_summary_html(overall, avg_score, period_label), unsafe_allow_html=True)

    # "vs previous equivalent period" — hidden when the prior window is thin.
    span = (end - start).days + 1
    prior = grading.summarize(apply_filters(
        grading.load_graded_range(start - timedelta(days=span), start - timedelta(days=1)),
        active))["overall"]
    st.markdown(period_comparison_html(overall, prior, f"previous {period_label.lower()}", min_sample),
                unsafe_allow_html=True)

    # --- Performance over time ---
    st.markdown('<div class="rz-section-head">Performance over time</div>', unsafe_allow_html=True)
    grp = st.query_params.get("grp", "daily")
    if grp not in ("daily", "weekly", "monthly"):
        grp = "daily"
    grp_pills = _pill_row("grp", [("daily", "Daily"), ("weekly", "Weekly"),
                                  ("monthly", "Monthly")], grp, "Group by")
    st.markdown(f'<div class="perf-controls">{grp_pills}</div>', unsafe_allow_html=True)
    _timeseries_chart(rows, grp)

    # --- Score calibration: does a higher score perform better? ---
    st.markdown('<div class="rz-section-head">Does a higher score perform better?</div>',
                unsafe_allow_html=True)
    bands = grading.summarize_by_band(rows, min_sample=min_sample)
    st.markdown(f'<div class="cal-interp">{calibration_interpretation(bands)}</div>',
                unsafe_allow_html=True)
    _calibration_chart(bands)
    st.markdown(calibration_table_html(bands, overall["hit_rate"]), unsafe_allow_html=True)

    st.markdown(
        '<div class="opp-disclaimer">Observed hit rates only — no “expected” rate is '
        'shown, because Score is a 0–100 ranking signal, not a win probability. Bands '
        'below the minimum sample are marked and de-emphasized.</div>',
        unsafe_allow_html=True)


def _series(rows: list[dict], grp: str) -> pd.DataFrame:
    """Per-period tallies (record, hit rate, sample, voids, pending)."""
    recs = []
    for r in rows:
        recs.append({"date": pd.to_datetime(r["snapshot_date"]),
                     "result": r.get("result") or "pending"})
    df = pd.DataFrame(recs)
    if df.empty:
        return df
    if grp == "weekly":
        df["period"] = df["date"].dt.to_period("W").dt.start_time
    elif grp == "monthly":
        df["period"] = df["date"].dt.to_period("M").dt.to_timestamp()
    else:
        df["period"] = df["date"]
    out = []
    for period, sub in df.groupby("period"):
        vc = sub["result"].value_counts()
        hit, miss, void = int(vc.get("hit", 0)), int(vc.get("miss", 0)), int(vc.get("void", 0))
        pending = len(sub) - hit - miss - void
        dec = hit + miss
        out.append({"period": period, "hit": hit, "miss": miss, "void": void,
                    "pending": pending, "sample": dec, "record": f"{hit}–{miss}",
                    "hit_rate": (hit / dec) if dec else None})
    return pd.DataFrame(out).sort_values("period").reset_index(drop=True)


def _timeseries_chart(rows: list[dict], grp: str) -> None:
    import altair as alt

    sdf = _series(rows, grp)
    if sdf.empty or sdf["sample"].sum() == 0:
        st.markdown('<div class="mlb-empty">No graded props to chart in this period.</div>',
                    unsafe_allow_html=True)
        return

    tips = [alt.Tooltip("period:T", title="Date"), alt.Tooltip("record:N", title="Record"),
            alt.Tooltip("hit_rate:Q", title="Hit rate", format=".1%"),
            alt.Tooltip("sample:Q", title="Graded"), alt.Tooltip("void:Q", title="Voids"),
            alt.Tooltip("pending:Q", title="Pending")]
    base = alt.Chart(sdf).encode(x=alt.X("period:T", title=""))
    volume = base.mark_bar(opacity=0.22, color="#7c8792").encode(
        y=alt.Y("sample:Q", axis=alt.Axis(title="Graded props", titleColor="#929ba7")),
        tooltip=tips)
    daily = base.mark_line(color="#8a9bb0", strokeWidth=1, opacity=0.55, point=alt.OverlayMarkDef(
        color="#8a9bb0", size=18)).encode(
        y=alt.Y("hit_rate:Q", axis=alt.Axis(format="%", title="Hit rate"),
                scale=alt.Scale(domain=[0, 1])), tooltip=tips)
    layers = [volume, daily]

    # Rolling-7 (daily grouping only), over a filled calendar range.
    if grp == "daily" and len(sdf) > 1:
        full = pd.date_range(sdf["period"].min(), sdf["period"].max(), freq="D")
        r = sdf.set_index("period").reindex(full)
        rh = r["hit"].fillna(0).rolling(7, min_periods=1).sum()
        rm = r["miss"].fillna(0).rolling(7, min_periods=1).sum()
        roll = pd.DataFrame({"period": full, "rolling": (rh / (rh + rm)).where((rh + rm) > 0).values})
        layers.append(alt.Chart(roll.dropna()).mark_line(color="#f4720f", strokeWidth=2.5).encode(
            x="period:T", y=alt.Y("rolling:Q", scale=alt.Scale(domain=[0, 1])),
            tooltip=[alt.Tooltip("period:T", title="Date"),
                     alt.Tooltip("rolling:Q", title="Rolling 7-day", format=".1%")]))

    chart = alt.layer(*layers).resolve_scale(y="independent").properties(height=260)
    st.altair_chart(chart, use_container_width=True)


def _calibration_chart(bands: dict) -> None:
    import altair as alt

    data = [{"band": label, "hit_rate": t["hit_rate"],
             "sample": t["hit"] + t["miss"], "small": bool(t.get("small_sample"))}
            for label, t in bands.items() if t["hit_rate"] is not None]
    if not data:
        return
    df = pd.DataFrame(data)
    order = [b["band"] for b in data]
    base = alt.Chart(df).encode(
        x=alt.X("band:N", sort=order, title="Score band", axis=alt.Axis(labelAngle=0)),
    )
    bars = base.mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        y=alt.Y("hit_rate:Q", title="Observed hit rate",
                axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
        color=alt.condition("datum.small", alt.value("#4b535e"), alt.value("#f4720f")),
        tooltip=[alt.Tooltip("band:N", title="Band"),
                 alt.Tooltip("hit_rate:Q", title="Hit rate", format=".1%"),
                 alt.Tooltip("sample:Q", title="Graded")],
    )
    labels = base.mark_text(dy=-8, color="#cdd2d9", fontSize=11).encode(
        y=alt.Y("hit_rate:Q"), text=alt.Text("hit_rate:Q", format=".0%"))
    samples = base.mark_text(dy=12, color="#929ba7", fontSize=10, baseline="top").encode(
        y=alt.value(0), text=alt.Text("sample:Q", format="d"))
    st.altair_chart((bars + labels + samples).properties(height=240), use_container_width=True)
