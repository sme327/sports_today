"""Results view: how past props actually graded out.

A dedicated destination (``?view=results&date=YYYY-MM-DD``) showing a past slate's
props graded hit / miss / void, filterable by sport, with a hit-rate summary. This
is the "did it work?" half of the loop — the served set (score above a threshold)
is shown; the full ledger underneath powers deeper analysis later.
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from components.league_filters import render_filters, selected_leagues
from components.results_feed import result_summary_html, results_feed_html
from leagues.base import get_adapter
from router import NavState
from services import grading

# Props scored above this counted as "what we'd have served" (Phase 2 makes it a
# control). The full population is still recorded for later analysis.
_SERVED_THRESHOLD = 75.0
_LEAGUE_NAMES = {"MLB": "MLB", "WNBA": "WNBA"}


def _date_stepper(d: date) -> str:
    yesterday = date.today() - timedelta(days=1)
    prev_d = (d - timedelta(days=1)).isoformat()
    next_d = d + timedelta(days=1)
    prev_link = f'<a class="rz-step" target="_self" href="?view=results&date={prev_d}">‹ Prev</a>'
    if next_d <= yesterday:
        next_link = f'<a class="rz-step" target="_self" href="?view=results&date={next_d.isoformat()}">Next ›</a>'
    else:
        next_link = '<span class="rz-step disabled">Next ›</span>'
    label = d.strftime("%A, %B %-d")
    return (f'<div class="rz-stepper">{prev_link}'
            f'<span class="rz-date">{label}</span>{next_link}</div>')


def render(nav: NavState) -> None:
    d = nav.results_date or (date.today() - timedelta(days=1))

    st.markdown('<a class="back-link" target="_self" href="?">← Back to today’s slate</a>',
                unsafe_allow_html=True)

    left, right = st.columns([3.5, 2.4], vertical_alignment="center")
    with left:
        st.markdown('<div class="page-title">Results</div>', unsafe_allow_html=True)
    with right:
        st.markdown(_date_stepper(d), unsafe_allow_html=True)

    # Grade any pending rows for this date (idempotent), then read the served set.
    try:
        grading.grade_slate(d)
    except Exception:
        pass  # grading must never break the page

    served = grading.load_graded_slate(d, min_score=_SERVED_THRESHOLD)
    if not served:
        st.markdown(
            '<div class="mlb-empty">No props were recorded for this date. The daily '
            'ledger fills in as you open the app each day; grades appear once the '
            'following day’s results are in.</div>',
            unsafe_allow_html=True)
        return

    # Sport filter (only leagues with props this date). Reuses the slate pills.
    leagues_present = sorted({r["league"] for r in served})
    adapters = [a for a in (get_adapter(lg) for lg in leagues_present) if a]
    render_filters(adapters)
    selected = selected_leagues(adapters)
    shown = [r for r in served if not selected or r["league"] in selected]

    # Summary — overall + per shown league.
    summary = grading.summarize(shown)
    st.markdown(result_summary_html(summary["overall"],
                                    f"All · props scored ≥ {int(_SERVED_THRESHOLD)}"),
                unsafe_allow_html=True)
    for lg in sorted(summary["by_league"]):
        st.markdown(result_summary_html(summary["by_league"][lg], _LEAGUE_NAMES.get(lg, lg)),
                    unsafe_allow_html=True)

    st.markdown(results_feed_html(shown), unsafe_allow_html=True)

    st.markdown(
        f'<div class="mlb-context">Graded from stored plate-appearance and box-score '
        f'results. Players who did not play are marked void and excluded from the hit '
        f'rate. Showing props we scored ≥ {int(_SERVED_THRESHOLD)}; the full scored '
        f'population is recorded underneath for longer-term analysis.</div>',
        unsafe_allow_html=True)
