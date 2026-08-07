"""Render graded prop results (pure HTML). One row per prop with a hit/miss/void
mark, the actual value the player recorded, and the score we gave it."""

from __future__ import annotations

import json
from html import escape

from domain import markets
from domain.markets import LABELS

_MARK = {"hit": "✓", "miss": "✗", "void": "∅", None: "…", "pending": "…"}

# Grade → (glyph, label). Icon + word so it never relies on color alone.
_GRADE = {"hit": ("✓", "HIT"), "miss": ("✗", "MISS"),
          "void": ("∅", "VOID"), "pending": ("◔", "PENDING")}


def _rate(tally: dict) -> str:
    """Hit rate as text, or 'Not graded' (never a bare 0% with nothing decided)."""
    return f'{tally["hit_rate"]:.1%}' if tally.get("hit_rate") is not None else "Not graded"


def _actual_display(row: dict) -> str:
    """The stat the player actually put up, phrased per market (via the registry)."""
    if row.get("result") == "void":
        return "did not play"
    val = row.get("actual_value")
    if val is None:
        return "pending"
    key = row.get("market_key") or markets.resolve(row.get("league"), row.get("market"))[0]
    return markets.actual_display(key, val)


def result_summary_html(summary: dict, label: str) -> str:
    """A compact chip line: 'MLB · 6 hit · 3 miss · 67% · 2 void'."""
    t = summary
    rate = f'<span class="rs-rate">{t["hit_rate"]:.0%} hit</span>' if t["hit_rate"] is not None else \
        '<span class="rs-rate muted">— not graded yet</span>'
    parts = [
        f'<span class="rs-label">{escape(label)}</span>',
        rate,
        f'<span class="rs-hit">{t["hit"]} hit</span>',
        f'<span class="rs-miss">{t["miss"]} miss</span>',
    ]
    if t["void"]:
        parts.append(f'<span class="rs-void">{t["void"]} void</span>')
    if t["pending"]:
        parts.append(f'<span class="rs-void">{t["pending"]} pending</span>')
    return '<div class="result-summary">' + '<span class="rs-dot">·</span>'.join(parts) + '</div>'


def market_breakdown_html(by_market: dict) -> str:
    """A titled group of per-market hit-rate chips (which markets convert?).

    ``by_market`` is ``{prop_type_key: tally}`` in canonical order (from
    ``grading.summarize_by_market``). Renders nothing for a single market — the
    overall summary already covers that case.
    """
    from domain.markets import LABELS

    if len(by_market) <= 1:
        return ""
    chips = "".join(result_summary_html(t, LABELS.get(pt, pt)) for pt, t in by_market.items())
    return ('<div class="rz-breakdown">'
            '<div class="rz-breakdown-head">By market</div>'
            f'{chips}</div>')


# ---------------------------------------------------- R2 — Daily Results v2 ---
def daily_summary_html(overall: dict, avg_score: float | None, total: int) -> str:
    """Compact metric row for the day. Hit rate is neutral (not green/red vs 50%)."""
    t = overall
    decided = t["hit"] + t["miss"]
    settled = decided + t["void"]
    rate = _rate(t)
    sample = f'<span class="ds-sub">n={decided}</span>' if decided else ""
    avg = f"{avg_score:.0f}" if avg_score is not None else "—"
    tiles = [
        ("Record", f'{t["hit"]}–{t["miss"]}', ""),
        ("Hit rate", rate, sample),
        ("Graded", str(decided), ""),
        ("Voids", str(t["void"]), ""),
        ("Pending", str(t["pending"]), ""),
        ("Avg score", avg, ""),
    ]
    cells = "".join(
        f'<div class="ds-tile"><div class="ds-label">{escape(l)}</div>'
        f'<div class="ds-value">{v}{sub}</div></div>' for l, v, sub in tiles)
    status = (f'{decided} of {settled} settled props graded'
              + (f' · {t["pending"]} pending' if t["pending"] else '')
              + f' · {total} total')
    return (f'<div class="daily-summary">{cells}</div>'
            f'<div class="ds-status">{escape(status)}</div>')


def market_table_html(by_market: dict, selected: str | None, sort_key: str) -> str:
    """Sortable 'By market' table; each row links to filter the prop list (preserving
    the other active filters). Sort by graded sample (default) or hit rate."""
    from components.filter_bar import filter_href

    if not by_market:
        return ""
    items = list(by_market.items())
    if sort_key == "rate":
        items.sort(key=lambda kv: (kv[1]["hit_rate"] is not None,
                                   kv[1]["hit_rate"] or 0), reverse=True)
    else:
        items.sort(key=lambda kv: kv[1]["hit"] + kv[1]["miss"], reverse=True)

    def hdr(key, label):
        arrow = " ↓" if sort_key == key else ""
        return (f'<a class="mkt-h sortable" target="_self" '
                f'href="{filter_href(msort=key)}">{label}{arrow}</a>')

    head = (f'<div class="mkt-row mkt-head">'
            f'<span class="mkt-h">Market</span>{hdr("sample", "Record / sample")}'
            f'{hdr("rate", "Hit rate")}<span class="mkt-h">Voids</span>'
            f'<span class="mkt-h">Pending</span></div>')
    rows = []
    for pt, t in items:
        decided = t["hit"] + t["miss"]
        sel = " selected" if pt == selected else ""
        rows.append(
            f'<a class="mkt-row{sel}" target="_self" href="{filter_href(mkt=pt)}">'
            f'<span class="mkt-name">{escape(LABELS.get(pt, pt))}</span>'
            f'<span class="mkt-rec">{t["hit"]}–{t["miss"]} <span class="ds-sub">'
            f'n={decided}</span></span>'
            f'<span class="mkt-rate">{_rate(t)}</span>'
            f'<span class="mkt-num">{t["void"]}</span>'
            f'<span class="mkt-num">{t["pending"]}</span></a>')
    return f'<div class="mkt-table">{head}{"".join(rows)}</div>'


def _evidence_list(raw) -> list[str]:
    try:
        v = json.loads(raw) if isinstance(raw, str) else (raw or [])
        return [str(x) for x in v] if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


def _prop_item(r: dict) -> str:
    result = r.get("result") or "pending"
    glyph, label = _GRADE.get(result, _GRADE["pending"])
    key = r.get("market_key") or markets.resolve(r.get("league"), r.get("market"))[0]
    rec = markets.recommendation_label(key, r.get("threshold"), r.get("direction")) if key else ""
    market_label = LABELS.get(markets.prop_type(r.get("league"), r.get("market")), r.get("market") or "")
    team = str(r.get("team_name") or "")
    opp = str(r.get("opponent") or "")
    vs = f'{escape(team)} vs {escape(opp)}' if opp else escape(team)
    actual = _actual_display(r)
    if result == "void" and r.get("void_reason"):
        actual = str(r["void_reason"])

    support = _evidence_list(r.get("support_evidence"))
    risk = _evidence_list(r.get("risk_evidence"))
    why = ""
    if support or risk:
        s = "".join(f"<li>{escape(x)}</li>" for x in support[:3])
        rk = (f'<div class="why-risk">Main risk: {escape(risk[0])}</div>' if risk else "")
        why = (f'<div class="prop-why"><div class="why-head">Why this score?</div>'
               f'<ul class="why-list">{s}</ul>{rk}</div>')

    return (
        f'<details class="prop-item r-{result}">'
        f'<summary class="prop-summary">'
        f'<span class="prop-grade r-{result}"><span class="pg-icon">{glyph}</span>{label}</span>'
        f'<span class="prop-id"><b>{escape(str(r.get("player_name") or "Unknown"))}</b>'
        f'<span class="prop-vs">{vs} · {escape(str(r.get("league") or ""))}</span></span>'
        f'<span class="prop-mkt">{escape(market_label)}<span class="prop-rec">Rec: {escape(rec)}</span></span>'
        f'<span class="prop-score">Score {int(r.get("opportunity_score") or 0)}</span>'
        f'<span class="prop-actual">Actual: {escape(actual)}</span>'
        f'</summary>{why}</details>')


def prop_list_html(rows: list[dict]) -> str:
    if not rows:
        return '<div class="mlb-empty">No props match the current filters.</div>'
    return f'<div class="prop-list">{"".join(_prop_item(r) for r in rows)}</div>'


# --------------------------------------------------- R4 — Score calibration ---
def calibration_table_html(bands: dict, overall_rate: float | None) -> str:
    """Per-band record / hit rate / sample / voids / diff-vs-overall, small-sample
    marked. ``bands`` is ordered low→high (from grading.summarize_by_band)."""
    if not bands:
        return '<div class="mlb-empty">No graded props in this period yet.</div>'
    head = ('<div class="cal-row cal-head"><span>Score band</span><span>Record</span>'
            '<span>Hit rate</span><span>Sample</span><span>Voids</span>'
            '<span>vs overall</span></div>')
    out = []
    for label, t in bands.items():
        dec = t["hit"] + t["miss"]
        diff = ""
        if t["hit_rate"] is not None and overall_rate is not None:
            pp = (t["hit_rate"] - overall_rate) * 100
            cls = "pos" if pp >= 0 else "neg"
            diff = f'<span class="cal-diff {cls}">{"+" if pp >= 0 else ""}{pp:.1f} pp</span>'
        badge = '<span class="cal-small">Small sample</span>' if t.get("small_sample") else ""
        out.append(
            f'<div class="cal-row"><span class="cal-band">{label}{badge}</span>'
            f'<span>{t["hit"]}–{t["miss"]}</span>'
            f'<span class="cal-rate">{_rate(t)}</span>'
            f'<span class="ds-sub">n={dec}</span><span>{t["void"]}</span><span>{diff}</span></div>')
    return f'<div class="cal-table">{head}{"".join(out)}</div>'


def calibration_interpretation(bands: dict) -> str:
    """A one-line read of the calibration, from the data only — never a claim a small
    sample can't support."""
    reliable = [(l, t) for l, t in bands.items()
                if not t.get("small_sample") and t["hit_rate"] is not None]
    small = [l for l, t in bands.items()
             if t.get("small_sample") and (t["hit"] + t["miss"]) > 0]
    note = (f" The {', '.join(small)} band{'s' if len(small) > 1 else ''} "
            f"remain{'' if len(small) > 1 else 's'} small.") if small else ""
    if len(reliable) < 2:
        return "Not enough graded props yet to judge whether higher scores perform better." + note
    rates = [t["hit_rate"] for _, t in reliable]   # bands ordered low → high
    trend = rates[-1] - rates[0]
    if trend > 0.03:
        return "Higher score bands have generally produced higher observed hit rates." + note
    if trend < -0.03:
        return "Higher score bands have not produced higher hit rates in this sample." + note
    return "Score bands have produced broadly similar hit rates so far." + note


def period_summary_html(overall: dict, avg_score: float | None, label: str) -> str:
    """A one-line record / hit-rate / sample headline for a period."""
    dec = overall["hit"] + overall["miss"]
    sample = f'<span class="ds-sub">n={dec}</span>' if dec else ""
    avg = f" · avg score {avg_score:.0f}" if avg_score is not None else ""
    return (f'<div class="perf-headline"><span class="ph-label">{escape(label)}</span>'
            f'<span class="ph-rec">{overall["hit"]}–{overall["miss"]}</span>'
            f'<span class="ph-rate">{_rate(overall)}</span>{sample}'
            f'<span class="ph-meta">{overall["void"]} void · {overall["pending"]} pending{avg}</span></div>')


def results_feed_html(rows: list[dict]) -> str:
    if not rows:
        return '<div class="mlb-empty">No graded props for this date and filter.</div>'
    items = []
    for r in rows:
        result = r.get("result") or "pending"
        team = f'<span class="result-team">{escape(str(r.get("team_name") or ""))}</span>' \
            if r.get("team_name") else ""
        items.append(
            f'<div class="result-row {escape(result)}">'
            f'<span class="result-mark {escape(result)}">{_MARK.get(r.get("result"), "…")}</span>'
            f'<div class="result-body">'
            f'<div class="result-player">{escape(str(r.get("player_name") or "Unknown"))} {team}</div>'
            f'<div class="result-market">{escape(str(r.get("market") or ""))}</div></div>'
            f'<div class="result-meta">'
            f'<div class="result-actual">{escape(_actual_display(r))}</div>'
            f'<div class="result-score">Score {int(r.get("opportunity_score") or 0)}</div>'
            f'</div></div>')
    return f'<div class="result-feed">{"".join(items)}</div>'
