"""Results view: how past props actually graded out.

A dedicated destination (``?view=results&date=YYYY-MM-DD``) showing a past slate's
props graded hit / miss / void — the "did it work?" half of the loop. Phase 2 adds
the tools to *learn* from it: a score-threshold control (does a higher bar convert
better?), a per-sport and per-market sub-filter, and per-market hit rates so you can
see which markets carry their weight. The full scored population is recorded
underneath; these controls slice it without changing what was stored.
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from components.league_filters import render_filters, selected_leagues
from components.prop_filters import (present_prop_types_rows, prop_type_of_row,
                                     render_prop_type_filters, selected_prop_types)
from components.results_feed import (market_breakdown_html, result_summary_html,
                                     results_feed_html)
from leagues.base import get_adapter
from router import NavState
from services import grading

_LEAGUE_NAMES = {"MLB": "MLB", "WNBA": "WNBA"}

# Score bands as inclusive [lo, hi] ranges. Most are minimums ("75+" → 75–100);
# the trailing two are *exact* scores (99, 100) so you can isolate how the very
# top of the distribution actually converts. (key, label, lo, hi).
_BANDS: list[tuple[str, str, float, float]] = [
    ("all", "All", 0.0, 100.0),
    ("75", "75+", 75.0, 100.0),
    ("85", "85+", 85.0, 100.0),
    ("90", "90+", 90.0, 100.0),
    ("95", "95+", 95.0, 100.0),
    ("99", "99", 99.0, 99.0),
    ("100", "100", 100.0, 100.0),
]
_DEFAULT_BAND = "75"
_BAND_RANGE = {k: (lo, hi) for k, _, lo, hi in _BANDS}


def _band_label(lo: float, hi: float) -> str:
    if lo <= 0 and hi >= 100:
        return "all scores"
    if lo == hi:
        return f"scored exactly {int(lo)}"
    return f"scored ≥ {int(lo)}"


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


def _threshold_control() -> tuple[float, float]:
    """Single-select band pills. Returns the active inclusive (lo, hi) score range."""
    st.session_state.setdefault("rz_threshold", _DEFAULT_BAND)
    active_key = st.session_state["rz_threshold"]
    st.markdown('<div class="rz-control-label">Score</div>', unsafe_allow_html=True)
    row = st.container(horizontal=True, gap="small")
    for key, label, _lo, _hi in _BANDS:
        if row.button(label, key=f"rz_band_{key}",
                      type="primary" if key == active_key else "secondary", width="content"):
            if key != active_key:
                st.session_state["rz_threshold"] = key
                st.rerun()
    return _BAND_RANGE.get(st.session_state["rz_threshold"], (0.0, 100.0))


def render(nav: NavState) -> None:
    d = nav.results_date or (date.today() - timedelta(days=1))

    st.markdown('<a class="back-link" target="_self" href="?">← Back to today’s slate</a>',
                unsafe_allow_html=True)

    left, right = st.columns([3.5, 2.4], vertical_alignment="center")
    with left:
        st.markdown('<div class="page-title">Results</div>', unsafe_allow_html=True)
    with right:
        st.markdown(_date_stepper(d), unsafe_allow_html=True)

    # Grade any pending rows for this date (idempotent), then read the full ledger.
    try:
        grading.grade_slate(d)
    except Exception:
        pass  # grading must never break the page

    population = grading.load_graded_slate(d)  # full scored population for this date
    if not population:
        st.markdown(
            '<div class="mlb-empty">No props were recorded for this date. The daily '
            'ledger fills in as you open the app each day; grades appear once the '
            'following day’s results are in.</div>',
            unsafe_allow_html=True)
        return

    # Sport filter (only leagues with props this date). Reuses the slate pills.
    leagues_present = sorted({r["league"] for r in population})
    adapters = [a for a in (get_adapter(lg) for lg in leagues_present) if a]
    render_filters(adapters)
    selected = selected_leagues(adapters)
    by_sport = [r for r in population if not selected or r["league"] in selected]

    # Market sub-filter — present types within the current sport selection.
    present = present_prop_types_rows(by_sport)
    render_prop_type_filters(present, key_prefix="rz_")
    chosen_types = selected_prop_types(present, key_prefix="rz_")
    by_market = [r for r in by_sport
                 if not chosen_types or prop_type_of_row(r) in chosen_types]

    # Score-band control (applies last, on top of sport + market).
    lo, hi = _threshold_control()
    shown = [r for r in by_market if lo <= (r.get("opportunity_score") or 0) <= hi]

    band_label = _band_label(lo, hi)
    if not shown:
        st.markdown(
            f'<div class="mlb-empty">No props match this filter ({band_label}). '
            'Widen the score band or clear a filter.</div>', unsafe_allow_html=True)
        return

    # Headline summary (respects every active filter), then per-league when >1 league.
    summary = grading.summarize(shown)
    st.markdown(result_summary_html(summary["overall"], f"All · {band_label}"),
                unsafe_allow_html=True)
    if len(summary["by_league"]) > 1:
        for lg in sorted(summary["by_league"]):
            st.markdown(result_summary_html(summary["by_league"][lg], _LEAGUE_NAMES.get(lg, lg)),
                        unsafe_allow_html=True)

    # Per-market hit rates — which markets actually convert (Phase 2 payoff).
    breakdown = market_breakdown_html(grading.summarize_by_market(shown))
    if breakdown:
        st.markdown(breakdown, unsafe_allow_html=True)

    st.markdown(results_feed_html(shown), unsafe_allow_html=True)

    st.markdown(
        f'<div class="mlb-context">Graded from stored plate-appearance and box-score '
        f'results. Players who did not play are marked void and excluded from the hit '
        f'rate. Showing {band_label}; the full scored population ({len(population)} props) '
        f'is recorded for longer-term analysis.</div>',
        unsafe_allow_html=True)
