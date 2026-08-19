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
def calibration_table_html(bands: dict, overall_rate: float | None,
                           band_base: dict | None = None) -> str:
    """Per-band record / hit rate / sample / voids / lift-over-base, small-sample marked.
    ``bands`` is ordered low→high (from grading.summarize_by_band).

    **Each band against its own base rate**, because the bands do not hold the same
    markets. The 99-100 band is 99% 1+ hit while the 70-74 band is half that, with a
    sixth SP hits and a fifth WNBA. Measured against one blended average, a band's score
    and its market mix are indistinguishable — the table would credit the top band for
    being full of a common event rather than for being well scored.
    """
    if not bands:
        return '<div class="mlb-empty">No graded props in this period yet.</div>'
    band_base = band_base or {}
    head = ('<div class="cal-row cal-head"><span>Score band</span><span>Record</span>'
            '<span>Hit rate</span><span>Sample</span><span>Voids</span>'
            '<span>vs base</span></div>')
    out = []
    for label, t in bands.items():
        dec = t["hit"] + t["miss"]
        diff = ""
        base = band_base.get(label)
        if t["hit_rate"] is not None and base is not None:
            pp = (t["hit_rate"] - base) * 100
            cls = "pos" if pp >= 0 else "neg"
            diff = (f'<span class="cal-diff {cls}">{"+" if pp >= 0 else ""}{pp:.1f} pp</span>'
                    f'<span class="et-prev"> base {base:.0%}</span>')
        badge = '<span class="cal-small">Small sample</span>' if t.get("small_sample") else ""
        out.append(
            f'<div class="cal-row"><span class="cal-band">{label}{badge}</span>'
            f'<span>{t["hit"]}–{t["miss"]}</span>'
            f'<span class="cal-rate">{_rate(t)}</span>'
            f'<span class="ds-sub">n={dec}</span><span>{t["void"]}</span><span>{diff}</span></div>')
    return f'<div class="cal-table">{head}{"".join(out)}</div>'


def calibration_interpretation(bands: dict, band_base: dict | None = None) -> str:
    """A one-line read of the calibration, from the data only — never a claim a small
    sample can't support.

    Reads the trend in **lift over each band's own base rate** when those are available.
    Raw band rates would let a shift in market mix read as a change in calibration: the
    top band is almost purely 1+ hit, whose event is far more common than a WNBA line's.
    """
    band_base = band_base or {}
    reliable = [(l, t) for l, t in bands.items()
                if not t.get("small_sample") and t["hit_rate"] is not None]
    small = [l for l, t in bands.items()
             if t.get("small_sample") and (t["hit"] + t["miss"]) > 0]
    note = (f" The {', '.join(small)} band{'s' if len(small) > 1 else ''} "
            f"remain{'' if len(small) > 1 else 's'} small.") if small else ""
    if len(reliable) < 2:
        return "Not enough graded props yet to judge whether higher scores perform better." + note
    if all(band_base.get(l) is not None for l, _ in reliable):
        rates = [t["hit_rate"] - band_base[l] for l, t in reliable]
    else:
        rates = [t["hit_rate"] for _, t in reliable]   # bands ordered low → high
    trend = rates[-1] - rates[0]
    if trend > 0.03:
        return "Higher score bands have generally produced higher observed hit rates." + note
    if trend < -0.03:
        return "Higher score bands have not produced higher hit rates in this sample." + note
    return "Score bands have produced broadly similar hit rates so far." + note


def period_summary_html(overall: dict, avg_score: float | None, label: str,
                        cohort: str | None = None, slates: int | None = None) -> str:
    """Record / hit-rate / sample headline for an explicitly named public cohort."""
    dec = overall["hit"] + overall["miss"]
    avg = f" · avg score {avg_score:.0f}" if avg_score is not None else ""
    sample = f'<span class="ds-sub">n={dec}</span>' if dec else ""
    slate_text = f" · {slates} slate{'s' if slates != 1 else ''}" if slates is not None else ""
    cohort_text = escape(cohort or "Predictions")
    return (f'<div class="perf-headline"><span class="ph-label">{escape(label)} · {cohort_text}</span>'
            f'<span class="ph-rec">{overall["hit"]}–{overall["miss"]}</span>'
            f'<span class="ph-rate">{_rate(overall)}</span>{sample}'
            f'<span class="ph-meta">{overall["void"]} void · {overall["pending"]} pending'
            f'{avg}{slate_text}</span></div>')


def cohort_comparison_html(qualifying: dict, featured: dict, other: dict) -> str:
    """Side-by-side model coverage and ranking check for the three public cohorts."""
    def cell(label: str, tally: dict) -> str:
        decided = tally["hit"] + tally["miss"]
        return (f'<div class="cohort-cell"><span>{escape(label)}</span>'
                f'<strong>{tally["hit"]}–{tally["miss"]}</strong>'
                f'<b>{_rate(tally)}</b><small>n={decided}</small></div>')
    return ('<div class="cohort-comparison" aria-label="Cohort comparison">'
            + cell("All qualifying", qualifying)
            + cell("Featured", featured)
            + cell("Other qualifying", other) + '</div>')


def market_trend_matrix_html(rows: list[dict], max_slates: int = 8) -> str:
    """One-view market pulse across recent graded slates.

    Cell color is relative to that market's own period average, so unlike raw score
    comparison it does not imply that different prop families share a baseline.
    """
    from datetime import date
    from domain.markets import ORDER, prop_type

    decided_rows = [r for r in rows if r.get("result") in {"hit", "miss"}]
    dates = sorted({str(r.get("snapshot_date")) for r in decided_rows
                    if r.get("snapshot_date")})[-max_slates:]
    if not dates:
        return '<div class="mlb-empty">No decided slates to chart in this period.</div>'

    by_market: dict[str, list[dict]] = {}
    for row in decided_rows:
        key = row.get("market_key") or prop_type(row.get("league"), row.get("market"))
        # market_key is more specific than the UI prop type for legacy rows.
        ui_key = prop_type(row.get("league"), row.get("market"))
        by_market.setdefault(ui_key or key, []).append(row)

    def rate(subset: list[dict]) -> tuple[float | None, int]:
        hit = sum(r.get("result") == "hit" for r in subset)
        miss = sum(r.get("result") == "miss" for r in subset)
        n = hit + miss
        return ((hit / n) if n else None, n)

    def date_label(token: str) -> str:
        try:
            parsed = date.fromisoformat(token)
            return f'{parsed.strftime("%b")}<b>{parsed.day}</b>'
        except ValueError:
            return escape(token)

    header_dates = "".join(
        f'<span class="mtp-date" role="columnheader">{date_label(token)}</span>'
        for token in dates)
    head = (f'<div class="mtp-row mtp-head" role="row"><span role="columnheader">Market</span>'
            f'{header_dates}<span role="columnheader">Period</span></div>')
    body = []
    for key in ORDER:
        market_rows = by_market.get(key, [])
        if not market_rows:
            continue
        overall, overall_n = rate(market_rows)
        league = next((r.get("league") for r in market_rows if r.get("league")), "")
        emoji = "⚾" if league == "MLB" else "🏀" if league in {"WNBA", "NBA"} else ""
        cells = []
        for token in dates:
            cell_rate, cell_n = rate([
                r for r in market_rows if str(r.get("snapshot_date")) == token
            ])
            if cell_rate is None:
                cells.append('<span class="mtp-cell empty" role="cell" aria-label="No decided predictions">—</span>')
                continue
            diff = cell_rate - (overall or 0)
            tone = "above" if diff >= .05 else "below" if diff <= -.05 else "near"
            small = " small" if cell_n < 5 else ""
            cells.append(
                f'<span class="mtp-cell {tone}{small}" role="cell" '
                f'title="{cell_rate:.0%} · n={cell_n} · {diff:+.0%} vs this market average" '
                f'aria-label="{cell_rate:.0%}, {cell_n} predictions">'
                f'<b>{cell_rate:.0%}</b><small>n={cell_n}</small></span>')

        recent_dates = set(dates[-3:])
        prior_dates = set(dates[-6:-3])
        recent_rate, recent_n = rate([r for r in market_rows
                                      if str(r.get("snapshot_date")) in recent_dates])
        prior_rate, prior_n = rate([r for r in market_rows
                                    if str(r.get("snapshot_date")) in prior_dates])
        if recent_rate is not None and prior_rate is not None and min(recent_n, prior_n) >= 10:
            delta = (recent_rate - prior_rate) * 100
            arrow = "↑" if delta >= 3 else "↓" if delta <= -3 else "→"
            trend_cls = "up" if delta >= 3 else "down" if delta <= -3 else "flat"
            trend = f'<small class="{trend_cls}">{arrow} {delta:+.0f} pp</small>'
        else:
            trend = '<small class="flat">building sample</small>'
        summary = (f'<span class="mtp-total" role="cell"><b>{overall:.0%}</b>'
                   f'<small>n={overall_n}</small>{trend}</span>')
        label = (f'<span class="mtp-market" role="rowheader"><i aria-hidden="true">{emoji}</i>'
                 f'{escape(LABELS.get(key, key))}</span>')
        body.append(f'<div class="mtp-row" role="row">{label}{"".join(cells)}{summary}</div>')

    if not body:
        return '<div class="mlb-empty">No market trend data matches these filters.</div>'
    return (f'<div class="market-trend-scroll"><div class="market-trend" role="table" '
            f'aria-label="Market hit rates by recent slate" style="--trend-cols:{len(dates)}">'
            f'{head}{"".join(body)}</div></div>'
            '<div class="mtp-legend"><span class="above">Above own average</span>'
            '<span class="near">Near own average</span><span class="below">Below own average</span>'
            '<span>Faded cells have fewer than 5 decisions</span></div>')


def _lift_html(rate: float | None, base: float | None) -> str:
    """Lift over this row's own base rate, with the base shown beside it.

    Empty when the base is unknown — a missing comparison is honest, and the alternative
    (falling back to the app-wide average) is the thing this replaced.
    """
    if rate is None or base is None:
        return '<span class="et-prev">—</span>'
    pp = (rate - base) * 100
    return (f'<span class="cal-diff {"pos" if pp >= 0 else "neg"}">'
            f'{"+" if pp >= 0 else ""}{pp:.1f} pp</span>'
            f'<span class="et-prev"> base {base:.0%}</span>')


def _diff_html(rate: float | None, overall: float | None) -> str:
    if rate is None or overall is None:
        return ""
    pp = (rate - overall) * 100
    return f'<span class="cal-diff {"pos" if pp >= 0 else "neg"}">{"+" if pp >= 0 else ""}{pp:.1f} pp</span>'


def edge_table_html(by_segment: dict, overall_rate: float | None, min_sample: int,
                    recent: dict, prev: dict, seg_base: dict | None = None) -> str:
    """Reliability-first edge table: segments meeting the min sample first, then a
    separated, marked 'below minimum sample' group — so a 3–0 never outranks a 55–40.

    **Ranked by lift over each segment's own base rate, not by hit rate.** A market whose
    event is naturally rare converts lower and is not thereby worse: WNBA assists hit 66%
    against a 35% base (+31), while 1+ hit hits 61% against a 61% base (+0.7). Sorting on
    the raw rate put them in the opposite order, and the old "vs overall" column — every
    market measured against one blended average — said the same wrong thing. That is
    [Method §1](../docs/engineering/METHOD.md); ``services/base_rates`` holds the reasoning
    and the populations.

    ``seg_base`` maps segment → its own base rate. Absent, the lift column stays empty
    rather than falling back to a comparison known to mislead.
    """
    if not by_segment:
        return '<div class="mlb-empty">No graded props to segment in this period.</div>'

    seg_base = seg_base or {}

    def dec(t):
        return t["hit"] + t["miss"]

    def lift(k, t):
        base = seg_base.get(k)
        return None if base is None or t["hit_rate"] is None else t["hit_rate"] - base

    def rank(kt):
        # Segments with no measurable base sort last rather than pretending to a 0 lift.
        return (lift(*kt) if lift(*kt) is not None else float("-inf"))
    meets = sorted(((k, t) for k, t in by_segment.items() if dec(t) >= min_sample),
                   key=rank, reverse=True)
    small = sorted(((k, t) for k, t in by_segment.items() if 0 < dec(t) < min_sample),
                   key=lambda kt: dec(kt[1]), reverse=True)

    def trend_cell(label):
        rc, pv = recent.get(label), prev.get(label)
        if rc is not None and pv is not None:
            dd = (rc - pv) * 100
            arrow = "↑" if dd > 3 else "↓" if dd < -3 else "→"
            return (f'<span class="et-trend">{arrow} {rc:.0%} '
                    f'<span class="et-prev">from {pv:.0%}</span></span>')
        if rc is not None:
            return f'<span class="et-trend">{rc:.0%} <span class="et-prev">30d</span></span>'
        return '<span class="et-prev">—</span>'

    def lift_cell(label, t):
        base = seg_base.get(label)
        if base is None or t["hit_rate"] is None:
            return '<span class="et-prev">—</span>'
        pp = (t["hit_rate"] - base) * 100
        cls = "pos" if pp >= 0 else "neg"
        # The base is shown, not just the difference: a lift means nothing without the
        # number it is a lift over, and this table exists because that number was hidden.
        return (f'<span class="cal-diff {cls}">{"+" if pp >= 0 else ""}{pp:.1f} pp</span>'
                f'<span class="et-prev"> base {base:.0%}</span>')

    def row(label, t, small_flag=False):
        badge = '<span class="cal-small">Small</span>' if small_flag else ""
        # Lift sits third so it survives the mobile rule, which hides columns 4 and 5.
        # It is the column the reader should act on, so it outranks the raw record.
        return (f'<div class="et-row"><span class="et-seg">{escape(str(label))}{badge}</span>'
                f'<span class="cal-rate">{_rate(t)} <span class="ds-sub">n={dec(t)}</span></span>'
                f'<span>{lift_cell(label, t)}</span>'
                f'<span>{t["hit"]}–{t["miss"]}</span>'
                f'<span>{trend_cell(label)}</span></div>')

    head = ('<div class="et-row et-head"><span>Segment</span><span>Hit rate</span>'
            '<span>vs base</span><span>Record</span><span>30-day trend</span></div>')
    body = "".join(row(k, t) for k, t in meets)
    if small:
        body += ('<div class="et-divider">Below minimum sample</div>'
                 + "".join(row(k, t, True) for k, t in small))
    return f'<div class="et-table">{head}{body}</div>'


def over_under_html(over_t: dict, under_t: dict, by_market: list) -> str:
    """Over-vs-Under comparison + a per-market breakdown."""
    def line(label, t):
        return (f'<div class="ou-line"><span class="ou-dir">{label}</span>'
                f'<span class="ou-rec">{t["hit"]}–{t["miss"]}</span>'
                f'<span class="ou-rate">{_rate(t)}</span>'
                f'<span class="ds-sub">n={t["hit"] + t["miss"]}</span></div>')
    diff = ""
    if over_t["hit_rate"] is not None and under_t["hit_rate"] is not None:
        pp = (over_t["hit_rate"] - under_t["hit_rate"]) * 100
        stronger = "Over stronger" if pp >= 0 else "Under stronger"
        diff = (f'<div class="ou-diff">Difference: <b>{"+" if pp >= 0 else ""}{pp:.1f} pp</b> '
                f'· {stronger}</div>')
    mrows = ""
    for label, ot, ut in by_market:
        if (ot["hit"] + ot["miss"] + ut["hit"] + ut["miss"]) == 0:
            continue
        mrows += (f'<div class="ou-mrow"><span class="ou-mname">{escape(label)}</span>'
                  f'<span>{_rate(ot)} <span class="ds-sub">n={ot["hit"] + ot["miss"]}</span></span>'
                  f'<span>{_rate(ut)} <span class="ds-sub">n={ut["hit"] + ut["miss"]}</span></span></div>')
    mtable = (f'<div class="ou-mtable"><div class="ou-mrow ou-mhead"><span>Market</span>'
              f'<span>Over</span><span>Under</span></div>{mrows}</div>') if mrows else ""
    return f'<div class="ou-wrap">{line("Over", over_t)}{line("Under", under_t)}{diff}{mtable}</div>'


def consistency_html(windows: list) -> str:
    """Side-by-side window cards (label, record, hit rate + sample). ``windows`` is
    an ordered list of (label, tally)."""
    cards = []
    for label, t in windows:
        dec = t["hit"] + t["miss"]
        sample = f'<span class="ds-sub">n={dec}</span>' if dec else ""
        cards.append(
            f'<div class="cons-card"><div class="cons-label">{escape(label)}</div>'
            f'<div class="cons-rate">{_rate(t)}</div>'
            f'<div class="cons-rec">{t["hit"]}–{t["miss"]} {sample}</div></div>')
    return f'<div class="cons-row">{"".join(cards)}</div>'


def monthly_table_html(months: list, overall_rate: float | None,
                       month_base: dict | None = None) -> str:
    """Chronological monthly table (record, hit rate, sample, lift over base) — is
    accuracy improving or deteriorating, without over-weighting single days.

    Each month against its own base rate, because the slate's league mix is seasonal: a
    month with a WNBA slate carries markets whose events are far rarer than 1+ hit, and
    against a single blended average that reads as the scorer improving.
    """
    if not months:
        return '<div class="mlb-empty">No graded months in range yet.</div>'
    month_base = month_base or {}
    head = ('<div class="et-row et-head"><span>Month</span><span>Record</span>'
            '<span>Hit rate</span><span>vs base</span><span></span></div>')
    body = "".join(
        f'<div class="et-row"><span class="et-seg">{escape(label)}</span>'
        f'<span>{t["hit"]}–{t["miss"]}</span>'
        f'<span class="cal-rate">{_rate(t)} <span class="ds-sub">n={t["hit"] + t["miss"]}</span></span>'
        f'<span>{_lift_html(t["hit_rate"], month_base.get(label))}</span><span></span></div>'
        for label, t in months)
    return f'<div class="et-table">{head}{body}</div>'


def version_table_html(groups: list, overall_rate: float | None) -> str:
    """Model versions grouped by market family.

    ``groups`` = the output of ``web.analytics._version_groups``. Each row shows the live
    version expanded; earlier versions of the same market collapse into one line, because
    fourteen version rows is a wall and the question a reader has is "did the change help
    *this* market", not "list everything ever stamped".

    Retired markets render in their own section on the rare occasions they appear at all.
    Performance shows what was *served*, and both retired markets were retired precisely
    because they could not clear the curation floor — total bases reached 70+ once in
    2,204 props, walks three times in 98 — so the cohort filter removes them upstream
    almost every time. The section exists so that when a row does survive, its record is
    not read as an old engine underperforming: the market was unservable, not the scorer.
    """
    if not groups:
        return '<div class="mlb-empty">No versioned props yet.</div>'

    def line(item, css, prefix=""):
        t = item["tally"]
        return (f'<div class="ver-row {css}">'
                f'<span class="et-seg">{escape(prefix + str(item["version"]))}</span>'
                f'<span class="ds-sub">{escape(item["first"])}→{escape(item["last"])}</span>'
                f'<span>{t["hit"]}–{t["miss"]}</span>'
                f'<span class="cal-rate">{_rate(t)} '
                f'<span class="ds-sub">n={t["hit"] + t["miss"]}</span></span>'
                f'<span>{_lift_html(t["hit_rate"], item.get("base"))}</span></div>')

    head = ('<div class="ver-row et-head"><span>Version</span><span>Active</span>'
            '<span>Record</span><span>Hit rate</span><span>vs base</span></div>')

    live, retired = [], []
    for group in groups:
        block = [f'<div class="ver-group-label">{escape(group["label"])}</div>']
        if group["current"]:
            block.append(line(group["current"], "ver-current"))
        earlier = group["earlier"]
        if earlier:
            t = group["earlier_tally"]
            span = f'{earlier[-1]["first"]}→{earlier[0]["last"]}'
            noun = "earlier version" if len(earlier) == 1 else "earlier versions"
            block.append(
                f'<div class="ver-row ver-earlier">'
                f'<span class="et-seg">{len(earlier)} {noun}</span>'
                f'<span class="ds-sub">{escape(span)}</span>'
                f'<span>{t["hit"]}–{t["miss"]}</span>'
                f'<span class="cal-rate">{_rate(t)} '
                f'<span class="ds-sub">n={t["hit"] + t["miss"]}</span></span>'
                f'<span>{_lift_html(t["hit_rate"], group.get("earlier_base"))}</span></div>')
        (retired if group["retired"] else live).append("".join(block))

    out = f'<div class="et-table">{head}{"".join(live)}</div>'
    if retired:
        out += ('<div class="ver-retired-head">Retired markets</div>'
                f'<div class="et-table">{"".join(retired)}</div>'
                '<div class="opp-disclaimer">No longer scored. Their specs are kept so '
                'graded history still resolves; the record reflects a market that could '
                'not clear the curation floor, not a scorer that underperformed.</div>')
    return out

def period_comparison_html(current: dict, prior: dict, prior_label: str,
                           min_sample: int) -> str:
    """"X% hit rate, up N.N percentage points vs previous 30 days" — hidden when the
    prior period has too few graded props to compare."""
    cr, pr = current.get("hit_rate"), prior.get("hit_rate")
    if cr is None or pr is None or (prior["hit"] + prior["miss"]) < min_sample:
        return ""
    pp = (cr - pr) * 100
    direction = "up" if pp >= 0 else "down"
    return (f'<div class="perf-compare">{cr:.1%} hit rate, '
            f'<span class="pc-{direction}">{direction} {abs(pp):.1f} percentage points</span> '
            f'vs {escape(prior_label)}</div>')


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
