"""Shared, query-param-driven filter bar for the Results / Performance views.

All state lives in the URL, so filters are shareable and stay in sync with the
market-table row clicks (which are just links). Each control is a compact pill
group; active filters show as removable chips with a Clear-all. Filtering itself
runs through ``apply_filters`` so every metric, table, chart, and row responds
identically.
"""

from __future__ import annotations

from html import escape
from urllib.parse import urlencode

import streamlit as st

from components.prop_filters import prop_type_of_row
from domain import markets
from domain.markets import LABELS, ORDER
from services.grading import SCORE_BANDS

# (param, label, [(value, display)]). "all" means the filter is off (param dropped).
_SPECS = [
    ("flg", "League", [("all", "All"), ("MLB", "MLB"), ("WNBA", "WNBA")]),
    ("mkt", "Market", [("all", "All")] + [(k, LABELS[k]) for k in ORDER]),
    ("bnd", "Score", [("all", "All")] + [(f"{lo}-{hi}", lbl) for lo, hi, lbl in SCORE_BANDS]),
    ("dir", "Direction", [("all", "All"), ("over", "Over"), ("under", "Under")]),
    ("res", "Result", [("all", "All"), ("hit", "Hit"), ("miss", "Miss"),
                       ("void", "Void"), ("pending", "Pending")]),
]
_LABEL_OF = {p: dict(opts) for p, _, opts in _SPECS}


def filter_href(date_iso: str, **overrides) -> str:
    """A results URL preserving the current filters/sort, with ``overrides`` applied
    (a value of ``"all"``/``None`` removes that param)."""
    params = {"view": "results", "date": date_iso}
    for k, v in st.query_params.to_dict().items():
        if k not in ("view", "date"):
            params[k] = v
    for p, v in overrides.items():
        if v in (None, "all"):
            params.pop(p, None)
        else:
            params[p] = v
    return "?" + urlencode(params)


def active_filters() -> dict:
    """Current filter values from the URL ({param: value}, 'all' when off)."""
    return {p: st.query_params.get(p, "all") for p, _, _ in _SPECS}


def _direction(r: dict) -> str:
    return r.get("direction") or markets.resolve(r.get("league"), r.get("market"))[1]


def apply_filters(rows: list[dict], active: dict) -> list[dict]:
    out = rows
    if active.get("flg", "all") != "all":
        out = [r for r in out if r.get("league") == active["flg"]]
    if active.get("mkt", "all") != "all":
        out = [r for r in out if prop_type_of_row(r) == active["mkt"]]
    if active.get("bnd", "all") != "all":
        lo, hi = (int(x) for x in active["bnd"].split("-"))
        out = [r for r in out if lo <= (r.get("opportunity_score") or -1) <= hi]
    if active.get("dir", "all") != "all":
        out = [r for r in out if _direction(r) == active["dir"]]
    if active.get("res", "all") != "all":
        out = [r for r in out if (r.get("result") or "pending") == active["res"]]
    return out


def filter_bar_html(date_iso: str, active: dict) -> str:
    """The pill-group filter bar + active-filter chips + Clear all."""
    groups = []
    for param, label, opts in _SPECS:
        cur = active.get(param, "all")
        pills = "".join(
            f'<a class="fb-pill{" active" if v == cur else ""}" target="_self" '
            f'href="{filter_href(date_iso, **{param: v})}">{escape(disp)}</a>'
            for v, disp in opts)
        groups.append(f'<div class="fb-group"><span class="fb-label">{label}</span>'
                      f'<span class="fb-pills">{pills}</span></div>')

    chips, n_active = [], 0
    for param, label, _opts in _SPECS:
        v = active.get(param, "all")
        if v != "all":
            n_active += 1
            chips.append(
                f'<span class="fb-chip">{escape(label)}: <b>{escape(_LABEL_OF[param].get(v, v))}</b>'
                f'<a class="fb-x" target="_self" href="{filter_href(date_iso, **{param: "all"})}">✕</a>'
                '</span>')
    chip_row = ""
    if n_active:
        chip_row = (f'<div class="fb-chips"><span class="fb-active-count">{n_active} active</span>'
                    f'{"".join(chips)}'
                    f'<a class="fb-clear" target="_self" href="?view=results&date={date_iso}">'
                    'Clear all</a></div>')

    return f'<div class="filter-bar">{"".join(groups)}</div>{chip_row}'
