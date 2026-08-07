"""Daily Results view (R2): how a past slate's props actually graded out.

``?view=results&date=YYYY-MM-DD`` — the "did it work?" half of the loop. Shows a
compact day summary, a sortable By-market table (click a row to filter), and the
individual props (recommendation vs. actual disambiguated, expandable "Why this
score?"). Grading is centralized in ``services.grading`` so this view and the
Performance view can never compute outcomes differently.
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from components.filter_bar import active_filters, apply_filters, filter_bar_html
from components.results_feed import (daily_summary_html, market_table_html,
                                     prop_list_html)
from router import NavState
from services import grading

_RESULT_ORDER = {"hit": 0, "miss": 1, "void": 2, None: 3, "pending": 3}
_SORTS = {
    "Score ↓": lambda r: -(r.get("opportunity_score") or 0),
    "Score ↑": lambda r: (r.get("opportunity_score") or 0),
    "Player": lambda r: str(r.get("player_name") or "").lower(),
    "Result": lambda r: _RESULT_ORDER.get(r.get("result"), 3),
}


def _goto(d: date) -> None:
    """Navigate to another results date, clearing per-date filters."""
    st.query_params.clear()
    st.query_params["view"] = "results"
    st.query_params["date"] = d.isoformat()
    st.rerun()


def _date_nav(d: date) -> None:
    yesterday = date.today() - timedelta(days=1)
    st.markdown('<div class="page-title">Results</div>', unsafe_allow_html=True)
    prev, pick, nxt, latest, _ = st.columns([0.5, 2.2, 0.5, 1.2, 4], vertical_alignment="center")
    if prev.button("‹", key="rz_prev", help="Previous day", width="stretch"):
        _goto(d - timedelta(days=1))
    picked = pick.date_input("Date", value=d, max_value=yesterday,
                             label_visibility="collapsed", format="YYYY-MM-DD")
    if picked and picked != d:
        _goto(picked)
    if nxt.button("›", key="rz_next", help="Next day", width="stretch",
                  disabled=d >= yesterday):
        _goto(d + timedelta(days=1))
    if d != yesterday:
        if latest.button("Latest →", key="rz_latest", width="stretch"):
            _goto(yesterday)


def render(nav: NavState) -> None:
    d = nav.results_date or (date.today() - timedelta(days=1))

    st.markdown('<div class="section-row">'
                '<a class="back-link" target="_self" href="?">← Back to today’s slate</a>'
                '<a class="results-link" target="_self" href="?view=performance">Performance →</a>'
                '</div>', unsafe_allow_html=True)
    _date_nav(d)

    try:
        grading.grade_slate(d)          # idempotent; grades any now-available rows
    except Exception:
        pass

    rows = grading.load_graded_slate(d)
    if not rows:
        st.markdown(
            '<div class="mlb-empty">No props were recorded for this date. The daily '
            'ledger fills in as you open the app each day; grades appear once the '
            'following day’s results are in.</div>', unsafe_allow_html=True)
        return

    # Shared filter bar — drives the summary, the by-market table, and the prop list.
    active = active_filters()
    st.markdown(filter_bar_html(active), unsafe_allow_html=True)
    filtered = apply_filters(rows, active)

    # Day summary (neutral hit-rate styling) over the filtered set.
    overall = grading.summarize(filtered)["overall"]
    scores = [r["opportunity_score"] for r in filtered if r.get("opportunity_score") is not None]
    avg_score = sum(scores) / len(scores) if scores else None
    st.markdown(daily_summary_html(overall, avg_score, len(filtered)), unsafe_allow_html=True)

    # By-market table — click a row to filter the prop list (preserves other filters).
    msort = st.query_params.get("msort", "sample")
    st.markdown('<div class="rz-section-head">By market</div>', unsafe_allow_html=True)
    st.markdown(market_table_html(grading.summarize_by_market(filtered), active.get("mkt"),
                                  msort), unsafe_allow_html=True)

    # Prop list controls: search + sort (the filter bar already narrowed the set).
    st.markdown('<div class="rz-section-head">Props</div>', unsafe_allow_html=True)
    c_search, c_sort = st.columns([3, 1.4], vertical_alignment="center")
    query = c_search.text_input("Search", placeholder="Search player or team…",
                                label_visibility="collapsed").strip().lower()
    sort = c_sort.selectbox("Sort", list(_SORTS), label_visibility="collapsed")

    props = filtered
    if query:
        props = [r for r in props
                 if query in str(r.get("player_name") or "").lower()
                 or query in str(r.get("team_name") or "").lower()
                 or query in str(r.get("opponent") or "").lower()]
    props = sorted(props, key=_SORTS[sort])

    st.markdown(f'<div class="opp-count">{len(props)} '
                f'{"prop" if len(props) == 1 else "props"}</div>', unsafe_allow_html=True)
    st.markdown(prop_list_html(props), unsafe_allow_html=True)

    st.markdown(
        '<div class="opp-disclaimer">Graded from stored plate-appearance and box-score '
        'results. Players who did not play are Void and excluded from the hit rate. '
        'Score is the model’s 0–100 ranking signal, not a win probability.</div>',
        unsafe_allow_html=True)
