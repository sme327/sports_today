"""Render graded prop results (pure HTML). One row per prop with a hit/miss/void
mark, the actual value the player recorded, and the score we gave it."""

from __future__ import annotations

import json
from html import escape
from urllib.parse import quote_plus

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


def market_table_html(by_market: dict, selected: str | None, sort_key: str,
                      date_iso: str) -> str:
    """Sortable 'By market' table; each row links to filter the prop list. Sort by
    graded sample (default) or hit rate; sample stays visible either way."""
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
                f'href="?view=results&date={date_iso}&msort={key}">{label}{arrow}</a>')

    head = (f'<div class="mkt-row mkt-head">'
            f'<span class="mkt-h">Market</span>{hdr("sample", "Record / sample")}'
            f'{hdr("rate", "Hit rate")}<span class="mkt-h">Voids</span>'
            f'<span class="mkt-h">Pending</span></div>')
    rows = []
    for pt, t in items:
        decided = t["hit"] + t["miss"]
        sel = " selected" if pt == selected else ""
        base = f"?view=results&date={date_iso}&mkt={quote_plus(pt)}"
        rows.append(
            f'<a class="mkt-row{sel}" target="_self" href="{base}">'
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
