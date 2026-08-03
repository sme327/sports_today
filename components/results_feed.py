"""Render graded prop results (pure HTML). One row per prop with a hit/miss/void
mark, the actual value the player recorded, and the score we gave it."""

from __future__ import annotations

from html import escape

_MARK = {"hit": "✓", "miss": "✗", "void": "∅", None: "…", "pending": "…"}


def _actual_display(row: dict) -> str:
    """The stat the player actually put up, phrased per market."""
    result = row.get("result")
    if result == "void":
        return "did not play"
    val = row.get("actual_value")
    if val is None:
        return "pending"
    market = (row.get("market") or "").lower()
    n = int(val) if float(val).is_integer() else val
    if "hit" in market:
        return f"{n} hit" if n == 1 else f"{n} hits"
    if "point" in market:
        return f"{n} pts"
    if "rebound" in market:
        return f"{n} reb"
    if "assist" in market:
        return f"{n} ast"
    return str(n)


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
