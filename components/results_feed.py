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


def _pts(value: float | None, *, signed: bool = True) -> str:
    """A percentage-point difference, in the one unit the Performance page uses.

    It used to be "pp" in the tables and "pts" in the generated sentences, on the one page
    whose central figure is a percentage-point difference. Two units for one quantity is
    a reading tax; ``services.model_trust.pts`` is the same formatter for prose.
    """
    if value is None:
        return "—"
    sign = "+" if (signed and value >= 0) else ""
    return f"{sign}{value * 100:.1f} pts"


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
# One sentence, used everywhere a score appears on this page. The score is a ranking
# signal; a reader who takes 93 for "93% likely" has been misled by us, not by the data.
SCORE_NOTE = ("Opportunity Score — our ranking signal, not a probability. 70 is the "
              "publication floor; a higher score means more estimated edge over the "
              "market's own base rate.")


def _note_icon(note: str = SCORE_NOTE) -> str:
    """A quiet 'i' carrying an explanation on hover, focus and to a screen reader."""
    safe = escape(note, quote=True)
    return (f'<span class="ds-info" tabindex="0" role="note" aria-label="{safe}" '
            f'title="{safe}">i</span>')


def daily_summary_html(overall: dict, avg_score: float | None, total: int) -> str:
    """The day's scorecard.

    Three metrics answer "how did we do" — record, hit rate, average score — and get the
    weight. Graded / void / pending answer "on how much", which only matters once the
    first three have been read, so they sit underneath in a quiet strip. Six equal tiles
    made the reader compare a hit rate against a void count.
    """
    t = overall
    decided = t["hit"] + t["miss"]
    avg = f"{avg_score:.0f}" if avg_score is not None else "—"
    primary = [
        ("Record", f'{t["hit"]}–{t["miss"]}', ""),
        ("Hit rate", _rate(t), ""),
        ("Avg score", avg, _note_icon()),
    ]
    cells = "".join(
        f'<div class="ds-tile"><div class="ds-label">{escape(label)}{extra}</div>'
        f'<div class="ds-value">{value}</div></div>' for label, value, extra in primary)
    minis = "".join(
        f'<span class="ds-mini"><span class="ds-mini-label">{escape(label)}</span>'
        f'<b>{value}</b></span>'
        for label, value in (("Graded", str(decided)), ("Void", str(t["void"])),
                             ("Pending", str(t["pending"]))))
    return (f'<div class="daily-summary">{cells}</div>'
            f'<div class="ds-secondary">{minis}'
            f'<span class="ds-mini ds-mini-total"><span class="ds-mini-label">Predictions'
            f'</span><b>{total}</b></span></div>')


def hit_rate_context_html(context: dict, *, min_prior: int = 30,
                          meaningful: float = 0.03) -> str:
    """One line placing today's hit rate against normal — the number it is worth judging against.

    Two comparisons, because either alone can mislead. The **hit rate** against the
    trailing 30 days is what a reader asks for. The **lift over base** is what the
    project actually measures on: a hit rate is a property of the props served as much
    as of the picking, so a day heavy in easy bars beats the average without anything
    having gone right. When the two disagree the second clause is where you see it.

    Colour is spent only on a difference worth acting on (``meaningful``, 3 points by
    default) and only when the trailing window has enough graded props to be a
    comparison at all — otherwise the line is neutral or absent.
    """
    rate, prior = context.get("day_rate"), context.get("prior_rate")
    if rate is None:
        return ""
    days = context.get("days", 30)
    parts = [f'<b>{rate:.1%}</b> today']
    if prior is not None and (context.get("prior_decided") or 0) >= min_prior:
        delta = rate - prior
        if abs(delta) < meaningful:
            parts.append(f'roughly in line with the {days}-day average ({prior:.1%})')
        else:
            tone = "up" if delta > 0 else "down"
            parts.append(f'<span class="hrc-{tone}">{_pts(delta)}</span> vs the '
                         f'{days}-day average ({prior:.1%})')
    day_lift, prior_lift = context.get("day_lift"), context.get("prior_lift")
    if day_lift is not None:
        clause = f'{_pts(day_lift)} over base'
        if prior_lift is not None:
            clause += f', where {days} days runs {_pts(prior_lift)}'
        note = ("Lift over base rate: how far the day beat the rate these exact props — "
                "this mix of markets, bars and sides — land at on their own.")
        parts.append(f'<span class="hrc-base" title="{escape(note, quote=True)}">'
                     f'{clause}</span>')
    if len(parts) == 1:
        return ""
    return ('<div class="hit-rate-context">'
            + '<span class="hrc-dot">·</span>'.join(parts) + '</div>')


def daily_read_html(read: dict) -> str:
    """The day in one to three sentences — what the numbers below it mean, not what they say.

    Every clause narrates a figure computed in ``web.analytics``; none is invented here.
    Observations are gated on sample and on size, so a day with nothing to say says
    nothing rather than filling three bullets with noise. The headline clause is
    mix-aware on purpose: "70.7%, best day in a week" is a sentence about which props
    were on offer at least as much as about the picking, and stating the raw number
    without the base rate beside it is the one comparison this project treats as a bug.
    """
    days = read.get("days", 30)
    decided = read.get("day_decided") or 0
    lift, prior_lift = read.get("day_lift"), read.get("prior_lift")
    day_base, prior_base = read.get("day_base"), read.get("prior_base")
    top_n, top_missed = read.get("top_n") or 0, read.get("top_missed") or 0
    items: list[str] = []

    # 1. The day itself, judged on lift rather than on the hit rate. A slate of low bars
    #    beats the average without anything having gone right, so the verdict is read off
    #    the base rate and the mix is named whenever it moved.
    if decided < (read.get("min_day") or 20):
        if decided:
            items.append(f'<strong>A short slate.</strong> {decided} graded prediction'
                         f'{"" if decided == 1 else "s"} is too few to read as a day — '
                         f'the rows below are a record, not a verdict.')
    elif lift is not None:
        # The verdict is absolute — did the picking beat what these props do unprompted —
        # and the trailing window is a second clause rather than the judgement. Grading a
        # day only against our own recent form would call a no-edge day "normal" on a bad
        # month, which is the flattering direction to be wrong in.
        verdict = ("A strong day" if lift >= .10 else "A good day" if lift >= .05
                   else "A modest day" if lift >= .02 else "No edge today" if lift > -.02
                   else "A poor day" if lift > -.08 else "A bad day")
        sentence = (f'<strong>{verdict}.</strong> Against what this exact mix of props '
                    f'lands on its own, the slate ran {_pts(lift)}')
        if prior_lift is not None:
            gap = lift - prior_lift
            stands = ("in line with" if abs(gap) < .03
                      else "ahead of" if gap > 0 else "behind")
            sentence += (f' — {stands} the {_pts(prior_lift)} the {days} days before it '
                         f'run.')
        else:
            sentence += '.'
        # Five points, not three: the two windows differ by a couple of points most days
        # (the league mix on a slate is not the league mix over a month), and a caveat
        # that fires most days stops being read.
        if day_base is not None and prior_base is not None and abs(day_base - prior_base) >= .05:
            easier = day_base > prior_base
            sentence += (f' The bars were {"lower" if easier else "higher"} than usual '
                         f'({day_base:.0%} of these props land unprompted against '
                         f'{prior_base:.0%} across that window), so the raw hit rate '
                         f'{"flatters" if easier else "understates"} the day.')
        items.append(sentence)

    # 2. Calibration: the day's highest-scored predictions against the day's own hit rate,
    #    which is the only comparison that isolates the scale from the slate. Measured
    #    across three weeks of ledger, that gap sits inside ±13 points on a normal day, so
    #    ±18 is the line at which it is saying something. A raw miss count is not: at a
    #    ~65% day rate, four misses in ten is the expectation, and flagging it every time
    #    trained the reader to skip the sentence.
    top_rate, rate = read.get("top_rate"), read.get("day_rate")
    if decided >= top_n > 0 and top_rate is not None and rate is not None:
        gap, top_hit = top_rate - rate, read.get("top_hit") or 0
        if top_missed == 0:
            items.append(f'<strong>The top of the scale held.</strong> All {top_n} of the '
                         f'day\'s highest-scored predictions landed, against {rate:.0%} '
                         f'across the slate.')
        elif gap >= .18:
            items.append(f'<strong>The top of the scale earned it.</strong> The {top_n} '
                         f'highest-scored predictions went {top_hit}–{top_missed}, well '
                         f'clear of the {rate:.0%} the slate hit overall.')
        elif gap <= -.18:
            items.append(f'<strong>The top of the scale did not hold.</strong> The {top_n} '
                         f'highest-scored predictions went {top_hit}–{top_missed} while the '
                         f'slate hit {rate:.0%} — the part of the scale that should be surest.')

    # 3. What drove it, either way. Two comparable markets or it is not a comparison, and
    #    a higher bar than the table's: a 6–2 market is a table row, not a day's story.
    #    Each clause states the sample it rests on rather than carrying a "small sample"
    #    label — on a single slate every number is a small sample, and a caveat that fires
    #    every time is read as decoration.
    ranked = [m for m in (read.get("markets") or [])
              if m.get("lift") is not None and m["decided"] >= (read.get("read_market") or 10)]
    if len(ranked) >= 2:
        ranked.sort(key=lambda m: -m["lift"])
        best, worst = ranked[0], ranked[-1]
        if best["lift"] >= .05:
            items.append(f'<strong>{escape(best["label"])}</strong> was the strongest '
                         f'market: {best["hit"]}–{best["miss"]}, {_pts(best["lift"])} '
                         f'over base on {best["decided"]} graded.')
        if worst["lift"] <= -.05:
            flatter = (worst["hit_rate"] or 0) >= .5
            items.append(
                f'<strong>{escape(worst["label"])}</strong> was the weak spot: '
                f'{worst["hit"]}–{worst["miss"]}'
                + (f' reads as a winning day, but props like these land more often than '
                   f'that unprompted — {_pts(worst["lift"])} on {worst["decided"]} graded.'
                   if flatter
                   else f', {_pts(worst["lift"])} against base on {worst["decided"]} graded.'))
    if not items:
        return ""
    bullets = "".join(f'<li>{item}</li>' for item in items[:3])
    return ('<section class="analytics-section daily-read">'
            '<h2>Daily read</h2>'
            f'<ul class="dr-list">{bullets}</ul></section>')


def market_table_html(rows: list[dict], *, min_lift_sample: int = 5) -> str:
    """Per-market record, hit rate, lift over base and average score.

    "We got 69% right" and "this market has predictive value" are different claims, and
    only the fourth column separates them: ``sp_hits`` unders convert ~78% of the time
    with nobody picking at all. Lift is shown only where enough props were decided to
    mean anything, and coloured only past ±5 points — a table where every cell is tinted
    ranks nothing.
    """
    if not rows:
        return ""
    head = ('<div class="mkt-row mkt-head"><span class="mkt-h">Market</span>'
            '<span class="mkt-h">Record</span><span class="mkt-h">Hit rate</span>'
            f'<span class="mkt-h">vs base</span><span class="mkt-h">Avg score'
            f'{_note_icon()}</span></div>')
    body = []
    for row in rows:
        decided = row["decided"]
        lift = row.get("lift")
        if lift is None or decided < min_lift_sample:
            lift_cell = '<span class="mkt-num mkt-lift">—</span>'
        else:
            tone = ("up" if lift >= .05 else "down" if lift <= -.05 else "flat")
            lift_cell = f'<span class="mkt-num mkt-lift {tone}">{_pts(lift)}</span>'
        void = f' <small class="mkt-flag">{row["void"]} void</small>' if row.get("void") else ""
        pending = (f' <small class="mkt-flag">{row["pending"]} pending</small>'
                   if row.get("pending") else "")
        avg = f'{row["avg_score"]:.0f}' if row.get("avg_score") is not None else "—"
        body.append(
            f'<div class="mkt-row"><span class="mkt-name">{escape(row["label"])}</span>'
            f'<span class="mkt-num">{row["hit"]}–{row["miss"]}'
            f'<small> n={decided}</small>{void}{pending}</span>'
            f'<span class="mkt-rate">{escape(row["hit_rate_display"])}</span>'
            f'{lift_cell}<span class="mkt-num">{avg}</span></div>')
    return f'<div class="mkt-table">{head}{"".join(body)}</div>'


def confident_misses_html(misses: list[dict], top_n: int, missed: int) -> str:
    """The day's highest-scored predictions that missed — calibration, not damage.

    Deliberately *not* the biggest numerical gaps: a 12-strikeout line missed by five is
    a worse-looking row than a 90-scored 1+ hit that went 0-for-4, and the second is the
    one that says something about the scale. Drawn from the ``top_n`` highest-scored
    predictions of the day, so "we were most sure about these" is the property being
    tested.
    """
    if not misses:
        return ""
    rows = "".join(
        f'<li><span class="cm-score">{int(row.get("opportunity_score") or 0)}</span>'
        f'<span class="cm-player">{escape(str(row.get("player_name") or "Unknown"))}</span>'
        f'<span class="cm-rec">{escape(row["market_label"])} '
        f'<b>{escape(row["recommendation"])}</b></span>'
        f'<span class="cm-actual"><i>actual</i> {escape(row["actual"])}</span></li>'
        for row in misses)
    plural = "" if missed == 1 else "es"
    return ('<div class="confident-misses">'
            f'<div class="cm-head">Highest-scored misses'
            f'<span class="cm-sub">{missed} miss{plural} among the day\'s {top_n} '
            f'strongest predictions</span></div>'
            f'<ul class="cm-list">{rows}</ul></div>')


def _evidence_list(raw) -> list[str]:
    try:
        v = json.loads(raw) if isinstance(raw, str) else (raw or [])
        return [str(x) for x in v] if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


def _prop_item(r: dict, index: int = 0) -> str:
    """One audit row: result, player, prediction, score, actual — in that order, aligned.

    The market used to be the loudest thing in the row (orange, on its own line, on every
    one of two hundred rows), which meant the column a reader scans for — did it hit —
    had to compete with the column they already know they are looking at. It is muted
    now; the posted line beside it carries the weight.

    The data attributes are the row's index card: the filter/sort controls read them
    rather than re-parsing the text, and the shortlist join reads the same ones it always
    did.
    """
    result = r.get("result") or "pending"
    glyph, label = _GRADE.get(result, _GRADE["pending"])
    key = r.get("market_key") or markets.resolve(r.get("league"), r.get("market"))[0]
    rec = markets.recommendation_label(key, r.get("threshold"), r.get("direction")) if key else ""
    prop_type = markets.prop_type_for(r.get("market_key"), r.get("league"), r.get("market"))
    market_label = LABELS.get(prop_type, r.get("market") or "")
    team = str(r.get("team_name") or "")
    opp = str(r.get("opponent") or "")
    vs = f'{escape(team)} vs {escape(opp)}' if opp else escape(team)
    actual = _actual_display(r)
    if result == "void" and r.get("void_reason"):
        actual = str(r["void_reason"])
    score = int(r.get("opportunity_score") or 0)

    support = _evidence_list(r.get("support_evidence"))
    risk = _evidence_list(r.get("risk_evidence"))
    why = ""
    if support or risk:
        s = "".join(f"<li>{escape(x)}</li>" for x in support[:3])
        rk = (f'<div class="why-risk">Main risk: {escape(risk[0])}</div>' if risk else "")
        why = (f'<div class="prop-why"><div class="why-head">Why this score?</div>'
               f'<ul class="why-list">{s}</ul>{rk}</div>')

    # The summary is five adjacent spans with no separators, so its accessible name ran
    # together as "✓HITPete AlonsoBaltimore Orioles vs Yankees · MLBBatter Hits". An
    # explicit label reads it as a sentence; the glyph is decorative beside the word it
    # duplicates, so it is hidden rather than announced as "check mark".
    spoken = (f'{label.title()} — {r.get("player_name") or "Unknown"}, '
              f'{team}{f" vs {opp}" if opp else ""}, {r.get("league") or ""}. '
              f'{market_label}, {rec}. Score {score}. '
              f'Actual: {actual}')
    # Join keys for the device-local shortlist ("Your picks: N/M"): raw stored
    # values, with the same market-key fallback the feed side uses when a legacy
    # scorer never set one, so both sides derive identical keys.
    join = (f'data-league="{escape(str(r.get("league") or ""), quote=True)}" '
            f'data-player-id="{escape(str(r.get("player_id") or ""), quote=True)}" '
            f'data-market-key="{escape(str(r.get("market_key") or r.get("market") or ""), quote=True)}" '
            f'data-result="{escape(result, quote=True)}" '
            f'data-market="{escape(prop_type, quote=True)}" '
            f'data-market-label="{escape(market_label, quote=True)}" '
            f'data-score="{score}" data-order="{index}" '
            f'data-player="{escape(str(r.get("player_name") or ""), quote=True)}"')
    return (
        f'<details class="prop-item r-{result}" {join}>'
        f'<summary class="prop-summary" aria-label="{escape(spoken, quote=True)}">'
        f'<span class="prop-grade r-{result}">'
        f'<span class="pg-icon" aria-hidden="true">{glyph}</span>{label}</span>'
        f'<span class="prop-id"><b>{escape(str(r.get("player_name") or "Unknown"))}</b>'
        f'<span class="prop-vs">{vs} · {escape(str(r.get("league") or ""))}</span></span>'
        f'<span class="prop-mkt"><i class="pm-name">{escape(market_label)}</i>'
        f'<b class="prop-rec">{escape(rec)}</b></span>'
        f'<span class="prop-score">{score}</span>'
        f'<span class="prop-actual">{escape(actual)}</span>'
        f'</summary>{why}</details>')


def prop_list_html(rows: list[dict]) -> str:
    if not rows:
        return '<div class="mlb-empty">No props match the current filters.</div>'
    head = ('<div class="prop-head" aria-hidden="true"><span>Result</span>'
            '<span>Player</span><span>Prediction</span>'
            f'<span>Score{_note_icon()}</span><span>Actual</span></div>')
    items = "".join(_prop_item(r, index) for index, r in enumerate(rows))
    return (f'{head}<div class="prop-list">{items}</div>'
            '<div class="mlb-empty prop-empty" hidden>No predictions match these filters.</div>')


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
            diff = (f'<span class="cal-diff {cls}">{"+" if pp >= 0 else ""}{pp:.1f} pts</span>'
                    f'<span class="et-prev"> base {base:.0%}</span>')
        badge = '<span class="cal-small">Small sample</span>' if t.get("small_sample") else ""
        out.append(
            f'<div class="cal-row"><span class="cal-band">{label}{badge}</span>'
            f'<span>{t["hit"]}–{t["miss"]}</span>'
            f'<span class="cal-rate">{_rate(t)}</span>'
            f'<span class="ds-sub">n={dec}</span><span>{t["void"]}</span><span>{diff}</span></div>')
    return f'<div class="cal-table">{head}{"".join(out)}</div>'


def calibration_bars_html(bands: dict, band_base: dict | None = None) -> str:
    """Hit rate per score band as bars, with each band's base rate marked on the bar.

    The bar length is the raw hit rate, because that is the thing a reader pictures. The
    **tick** is the rate that band's props convert on their own, so the visible gap
    between tick and bar end *is* the lift — the figure the table states in numbers. A
    plain hit-rate bar chart would have been the page's worst possible visual: the top
    band is almost purely 1+ hit, so it would show the longest bar for the band with the
    easiest events, which is the exact inference this page exists to prevent.

    No line is drawn between the bands. A line asserts a continuous relationship, and
    across seven bands of very different samples the data does not support one; bars make
    a calibration failure visible without claiming a trend that isn't there.
    """
    if not bands:
        return ""
    band_base = band_base or {}
    rows = []
    for label, t in bands.items():
        dec = t["hit"] + t["miss"]
        if t["hit_rate"] is None or not dec:
            continue
        rate = t["hit_rate"]
        base = band_base.get(label)
        lift = None if base is None else rate - base
        tone = ("pos" if lift >= 0.02 else "neg" if lift <= -0.02 else "flat") \
            if lift is not None else "flat"
        mark = (f'<i class="cb-base" style="left:{min(max(base, 0), 1):.4%}" '
                f'aria-hidden="true"></i>' if base is not None else "")
        small = ' cb-small' if t.get("small_sample") else ""
        spoken = (f'{label}: {rate:.0%} hit rate on {dec} graded predictions'
                  + (f', base rate {base:.0%}, {_pts(lift)} over base' if lift is not None else ""))
        rows.append(
            f'<div class="cb-row{small}">'
            f'<span class="cb-band">{label}</span>'
            f'<span class="cb-track" role="img" aria-label="{escape(spoken, quote=True)}">'
            f'<i class="cb-fill {tone}" style="width:{min(max(rate, 0), 1):.4%}"></i>{mark}</span>'
            f'<span class="cb-rate">{rate:.1%}</span>'
            f'<span class="cb-n">n={dec:,}</span></div>')
    if not rows:
        return ""
    return (f'<div class="cal-bars">{"".join(rows)}</div>'
            '<div class="mtp-legend"><span class="cb-key-fill">Observed hit rate</span>'
            '<span class="cb-key-base">Base rate for that band’s props — the gap is the '
            'edge</span></div>')


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


def market_trend_matrix_html(rows: list[dict], max_slates: int = 8,
                             base_of=None) -> str:
    """One-view market pulse across recent graded slates.

    Cell colour is relative to that market's own period figure, so it never implies that
    different prop families share a baseline.

    ``base_of(row) -> float | None`` supplies each prop's base rate, and when given, the
    comparison is **lift against lift** rather than rate against rate. That matters where
    a market's bar mix moves between days: `batter_hit` has a single bar so its base never
    moves (sd 0.000), but WNBA assists ranged from a .07 base to a .55 base across days
    (sd 0.104). A 40% day was being coloured identically in both cases, when one is
    outstanding and the other poor — and those are the app's three best markets.
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

    def _mean_base(subset: list[dict]) -> float | None:
        if base_of is None:
            return None
        values = [b for b in (base_of(r) for r in subset) if b is not None]
        return sum(values) / len(values) if values else None

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

    # Reading order is summary-first, then most recent, counting back. `dates` stays
    # chronological because the recent-vs-prior trend below depends on it; only the
    # display order reverses. On a phone the columns that matter are then the ones on
    # screen, and older slates scroll off to the right instead of pushing them there.
    shown_dates = list(reversed(dates))
    header_dates = "".join(
        f'<span class="mtp-date" role="columnheader">{date_label(token)}</span>'
        for token in shown_dates)
    head = (f'<div class="mtp-row mtp-head" role="row"><span role="columnheader">Market</span>'
            f'<span role="columnheader">Period</span>'
            f'<span role="columnheader">Trend</span>{header_dates}</div>')
    body = []
    for key in ORDER:
        market_rows = by_market.get(key, [])
        if not market_rows:
            continue
        overall, overall_n = rate(market_rows)
        overall_base = _mean_base(market_rows)
        base_lift = (None if overall is None or overall_base is None
                     else overall - overall_base)
        league = next((r.get("league") for r in market_rows if r.get("league")), "")
        emoji = "⚾" if league == "MLB" else "🏀" if league in {"WNBA", "NBA"} else ""
        cells = []
        for index, token in enumerate(shown_dates):
            cell_rate, cell_n = rate([
                r for r in market_rows if str(r.get("snapshot_date")) == token
            ])
            if cell_rate is None:
                cells.append(f'<span class="mtp-cell empty" role="cell" style="--age:{index}" '
                             f'aria-label="No decided predictions">—</span>')
                continue
            diff = cell_rate - (overall or 0)
            if base_lift is not None:
                cell_base = _mean_base([r for r in market_rows
                                        if str(r.get("snapshot_date")) == token])
                if cell_base is not None:
                    diff = (cell_rate - cell_base) - base_lift
            tone = "above" if diff >= .05 else "below" if diff <= -.05 else "near"
            small = " small" if cell_n < 5 else ""
            # Older slates read progressively quieter. Eight equally saturated columns
            # made a row of ordinary variance look like a row of findings; the point of
            # the grid is the *shape* of the recent run, and the newest slate is the one
            # a reader is asking about.
            cells.append(
                f'<span class="mtp-cell {tone}{small}" role="cell" '
                f'style="--age:{index}" '
                f'title="{cell_rate:.0%} · n={cell_n} · {diff * 100:+.0f} pts vs this market average" '
                f'aria-label="{cell_rate:.0%}, {cell_n} predictions">'
                f'<b>{cell_rate:.0%}</b><small>n={cell_n}</small></span>')

        recent_dates = set(dates[-3:])
        prior_dates = set(dates[-6:-3])
        recent_rate, recent_n = rate([r for r in market_rows
                                      if str(r.get("snapshot_date")) in recent_dates])
        prior_rate, prior_n = rate([r for r in market_rows
                                    if str(r.get("snapshot_date")) in prior_dates])
        # Change gets its own column, because "is this market improving or deteriorating"
        # is the question a row of eight percentages cannot answer at a glance. It stays
        # gated on both windows carrying ten decisions: a two-slate WNBA week swinging
        # twenty points is the sample talking, not the market.
        if recent_rate is not None and prior_rate is not None and min(recent_n, prior_n) >= 10:
            delta = (recent_rate - prior_rate) * 100
            arrow = "↑" if delta >= 3 else "↓" if delta <= -3 else "→"
            trend_cls = "up" if delta >= 3 else "down" if delta <= -3 else "flat"
            trend = (f'<span class="mtp-trend {trend_cls}" role="cell" '
                     f'aria-label="latest three slates {delta:+.0f} points against the '
                     f'prior three"><b>{arrow} {delta:+.0f}</b><small>vs prior 3</small></span>')
        else:
            trend = ('<span class="mtp-trend flat" role="cell">'
                     '<small>building sample</small></span>')
        summary = (f'<span class="mtp-total" role="cell"><b>{overall:.0%}</b>'
                   f'<small>n={overall_n}</small></span>')
        label = (f'<span class="mtp-market" role="rowheader"><i aria-hidden="true">{emoji}</i>'
                 f'{escape(LABELS.get(key, key))}</span>')
        body.append(f'<div class="mtp-row" role="row">{label}{summary}{trend}'
                    f'{"".join(cells)}</div>')

    if not body:
        return '<div class="mlb-empty">No market trend data matches these filters.</div>'
    return (f'<div class="market-trend-scroll"><div class="market-trend" role="table" '
            f'aria-label="Market hit rates by recent slate" style="--trend-cols:{len(dates)}">'
            f'{head}{"".join(body)}</div></div>'
            '<div class="mtp-legend"><span class="above">Above own average</span>'
            '<span class="near">Near own average</span><span class="below">Below own average</span>'
            '<span>Older slates fade; faded cells also have fewer than 5 decisions</span>'
            '</div>')


def _lift_html(rate: float | None, base: float | None) -> str:
    """Lift over this row's own base rate, with the base shown beside it.

    Empty when the base is unknown — a missing comparison is honest, and the alternative
    (falling back to the app-wide average) is the thing this replaced.
    """
    if rate is None or base is None:
        return '<span class="et-prev">—</span>'
    pp = (rate - base) * 100
    # Inside ±2 points the row stays grey. Green on a +0.4 asserts an edge the number
    # cannot carry, and this page is read for exactly that distinction.
    cls = "pos" if pp >= 2 else "neg" if pp <= -2 else "flat"
    return (f'<span class="cal-diff {cls}">'
            f'{"+" if pp >= 0 else ""}{pp:.1f} pts</span>'
            f'<span class="et-prev"> base {base:.0%}</span>')


def _diff_html(rate: float | None, overall: float | None) -> str:
    if rate is None or overall is None:
        return ""
    pp = (rate - overall) * 100
    return f'<span class="cal-diff {"pos" if pp >= 0 else "neg"}">{"+" if pp >= 0 else ""}{pp:.1f} pp</span>'


def edge_table_html(by_segment: dict, overall_rate: float | None, min_sample: int,
                    recent: dict, prev: dict, seg_base: dict | None = None) -> str:
    """Where the model has edge: segments ranked by lift, reliable ones separated from
    small-sample ones — so a 3–0 never sits in the same list as a 931–472.

    **Ranked by lift over each segment's own base rate, not by hit rate.** A market whose
    event is naturally rare converts lower and is not thereby worse: WNBA assists hit 66%
    against a 35% base (+31), while 1+ hit hits 61% against a 61% base (+0.7). Sorting on
    the raw rate put them in the opposite order, and the old "vs overall" column — every
    market measured against one blended average — said the same wrong thing. That is
    [Method §1](../docs/engineering/METHOD.md); ``services/base_rates`` holds the reasoning
    and the populations.

    **The two groups are titled, not merely divided.** "Reliable edges" and "Small-sample
    signals" say what the split means; the old "Below minimum sample" rule left a reader
    to infer that a 64% row with n=22 had been *discovered*, when the honest reading is
    that it has not yet been measured. Sample size is a headline in this table, never a
    footnote.

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
                   key=rank, reverse=True)

    def trend_cell(label):
        rc, pv = recent.get(label), prev.get(label)
        if rc is not None and pv is not None:
            dd = (rc - pv) * 100
            arrow = "↑" if dd > 3 else "↓" if dd < -3 else "→"
            cls = "up" if dd > 3 else "down" if dd < -3 else "flat"
            return (f'<span class="et-trend {cls}">{arrow} {dd:+.1f}'
                    f'<span class="et-prev"> from {pv:.0%}</span></span>')
        # No comparable prior period is its own answer, and a truthful one. It used to
        # print this period's rate labelled "30d" — the number the row already shows.
        return '<span class="et-prev">no prior period</span>'

    def lift_cell(label, t):
        base = seg_base.get(label)
        if base is None or t["hit_rate"] is None:
            return '<span class="et-prev">—</span>'
        pp = (t["hit_rate"] - base) * 100
        cls = "pos" if pp >= 2 else "neg" if pp <= -2 else "flat"
        # The base is shown, not just the difference: a lift means nothing without the
        # number it is a lift over, and this table exists because that number was hidden.
        return (f'<b class="cal-diff {cls}">{"+" if pp >= 0 else ""}{pp:.1f} pts</b>'
                f'<span class="et-prev"> base {base:.0%}</span>')

    def row(label, t, small_flag=False):
        badge = '<span class="cal-small">Small sample</span>' if small_flag else ""
        # Lift sits second so it survives the mobile rule, which hides the later columns.
        # It is the column the reader should act on, so it outranks the raw record.
        return (f'<div class="et-row{" et-row-small" if small_flag else ""}">'
                f'<span class="et-seg">{escape(str(label))}{badge}</span>'
                f'<span>{lift_cell(label, t)}</span>'
                f'<span class="cal-rate">{_rate(t)}</span>'
                f'<span class="et-n">n={dec(t):,}</span>'
                f'<span>{t["hit"]}–{t["miss"]}</span>'
                f'<span>{trend_cell(label)}</span></div>')

    head = ('<div class="et-row et-head"><span>Segment</span><span>vs base</span>'
            '<span>Hit rate</span><span>N</span><span>Record</span>'
            '<span>vs prior period</span></div>')
    body = ""
    if meets:
        body += (f'<div class="et-divider et-divider-strong">Reliable edges'
                 f'<small>n ≥ {min_sample} graded</small></div>'
                 + "".join(row(k, t) for k, t in meets))
    if small:
        body += ('<div class="et-divider">Small-sample signals'
                 f'<small>under {min_sample} graded — not yet a measured edge</small></div>'
                 + "".join(row(k, t, True) for k, t in small))
    return f'<div class="et-table et-table-6">{head}{body}</div>'


def over_under_html(over_t: dict, under_t: dict, by_market: list,
                    direction_lift: dict | None = None,
                    market_lift: dict | None = None) -> str:
    """Over-vs-Under, in lift as well as in hit rate, plus a per-market breakdown.

    **The two sides do not share a base rate**, so the raw difference between them is not
    a fact about the model. Overs are mostly 1+ hit at a ~61% base; unders are mostly SP
    hits allowed at ~48%. "Over hits 64%, Under 58%" therefore reads as a six-point edge
    for overs when the truth over the same rows is closer to the reverse. The lift line is
    the honest comparison, so it is shown at the same weight as the rate.
    """
    direction_lift = direction_lift or {}
    market_lift = market_lift or {}

    def line(label, t, key):
        lift = direction_lift.get(key)
        lift_html = ""
        if lift is not None:
            pp = lift[0] * 100 if isinstance(lift, tuple) else lift * 100
            cls = "pos" if pp >= 2 else "neg" if pp <= -2 else "flat"
            lift_html = (f'<span class="ou-lift cal-diff {cls}">'
                         f'{"+" if pp >= 0 else ""}{pp:.1f} pts</span>'
                         f'<span class="et-prev"> vs base</span>')
        return (f'<div class="ou-line"><span class="ou-dir">{label}</span>'
                f'<span class="ou-rec">{t["hit"]}–{t["miss"]}</span>'
                f'<span class="ou-rate">{_rate(t)}</span>'
                f'<span class="ou-liftwrap">{lift_html}</span>'
                f'<span class="ds-sub">n={t["hit"] + t["miss"]:,}</span></div>')

    def cell(label, t, side):
        dec = t["hit"] + t["miss"]
        if not dec:
            return '<span class="et-prev">—</span>'
        lift = market_lift.get((label, side))
        lift_html = ""
        if lift is not None:
            pp = lift * 100
            cls = "pos" if pp >= 2 else "neg" if pp <= -2 else "flat"
            lift_html = (f'<span class="cal-diff {cls}">'
                         f'{"+" if pp >= 0 else ""}{pp:.1f}</span>')
        return (f'{_rate(t)} {lift_html}<span class="ds-sub">n={dec:,}</span>')

    mrows = ""
    for label, ot, ut in by_market:
        if (ot["hit"] + ot["miss"] + ut["hit"] + ut["miss"]) == 0:
            continue
        mrows += (f'<div class="ou-mrow"><span class="ou-mname">{escape(label)}</span>'
                  f'<span>{cell(label, ot, "over")}</span>'
                  f'<span>{cell(label, ut, "under")}</span></div>')
    mtable = (f'<div class="ou-mtable"><div class="ou-mrow ou-mhead"><span>Market</span>'
              f'<span>Over<small>rate · pts vs base</small></span>'
              f'<span>Under<small>rate · pts vs base</small></span></div>'
              f'{mrows}</div>') if mrows else ""
    return (f'<div class="ou-wrap">{line("Over", over_t, "over")}'
            f'{line("Under", under_t, "under")}{mtable}</div>')


def consistency_html(windows: list) -> str:
    """Window cards, each carrying its change against the window it should be read against.

    ``windows`` is an ordered list of ``{"label", "tally", "vs", "delta"}``. The delta is
    what makes the row interpretable: five hit rates in a line invite the reader to do the
    subtraction, and the two subtractions worth doing (latest week against the month, the
    month against the one before) are the only two shown. The rest carry no delta rather
    than an arbitrary one.
    """
    cards = []
    for window in windows:
        t = window["tally"]
        dec = t["hit"] + t["miss"]
        sample = f'<span class="ds-sub">n={dec:,}</span>' if dec else ""
        delta, against = window.get("delta"), window.get("vs")
        if delta is not None and against:
            pp = delta * 100
            cls = "pos" if pp >= 1 else "neg" if pp <= -1 else "flat"
            change = (f'<div class="cons-delta"><span class="cal-diff {cls}">'
                      f'{"+" if pp >= 0 else ""}{pp:.1f} pts</span> '
                      f'<span class="et-prev">vs {escape(against)}</span></div>')
        else:
            change = '<div class="cons-delta"><span class="et-prev">—</span></div>'
        cards.append(
            f'<div class="cons-card"><div class="cons-label">{escape(window["label"])}</div>'
            f'<div class="cons-rate">{_rate(t)}</div>'
            f'<div class="cons-rec">{t["hit"]}–{t["miss"]} {sample}</div>{change}</div>')
    return f'<div class="cons-row">{"".join(cards)}</div>'


def _sparkline(values: list[float], labels: list[str], *, zero: bool = True) -> str:
    """A small inline SVG of a series, with a zero rule when the series is a lift.

    Deliberately unlabelled and unscaled: it is a shape, and the table beside it holds
    every number. A sparkline that invited reading values off it would be a chart, and a
    chart of six months of mixed league mix is a claim this data cannot support.
    """
    if len(values) < 2:
        return ""
    lo, hi = min(values + ([0.0] if zero else [])), max(values + ([0.0] if zero else []))
    span = (hi - lo) or 1.0
    width, height = 132, 30
    step = width / (len(values) - 1)

    def y(value):
        return height - 3 - ((value - lo) / span) * (height - 6)

    points = " ".join(f"{index * step:.1f},{y(value):.1f}"
                      for index, value in enumerate(values))
    rule = (f'<line x1="0" y1="{y(0):.1f}" x2="{width}" y2="{y(0):.1f}" '
            f'class="spark-zero"/>' if zero and lo <= 0 <= hi else "")
    last = (f'<circle cx="{(len(values) - 1) * step:.1f}" cy="{y(values[-1]):.1f}" r="2.4" '
            f'class="spark-dot"/>')
    spoken = ", ".join(f"{label} {value * 100:+.1f}"
                       for label, value in zip(labels, values))
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}" role="img" '
            f'aria-label="Lift over base by month: {escape(spoken, quote=True)}">'
            f'{rule}<polyline points="{points}" class="spark-line"/>{last}</svg>')


def monthly_table_html(months: list, overall_rate: float | None,
                       month_base: dict | None = None) -> str:
    """Chronological monthly table (record, hit rate, sample, lift over base) — is
    accuracy improving or deteriorating, without over-weighting single days.

    Each month against its own base rate, because the slate's league mix is seasonal: a
    month with a WNBA slate carries markets whose events are far rarer than 1+ hit, and
    against a single blended average that reads as the scorer improving. The sparkline
    plots that lift, never the raw rate, for the same reason.
    """
    if not months:
        return '<div class="mlb-empty">No graded months in range yet.</div>'
    month_base = month_base or {}
    lifts, labels = [], []
    for label, t in months:
        base = month_base.get(label)
        if base is not None and t["hit_rate"] is not None:
            lifts.append(t["hit_rate"] - base)
            labels.append(label)
    spark = _sparkline(lifts, labels)
    head = ('<div class="et-row et-head"><span>Month</span><span>Record</span>'
            '<span>Hit rate</span><span>vs base</span><span></span></div>')
    body = "".join(
        f'<div class="et-row"><span class="et-seg">{escape(label)}</span>'
        f'<span>{t["hit"]}–{t["miss"]}</span>'
        f'<span class="cal-rate">{_rate(t)} <span class="ds-sub">n={t["hit"] + t["miss"]:,}</span></span>'
        f'<span>{_lift_html(t["hit_rate"], month_base.get(label))}</span><span></span></div>'
        for label, t in months)
    trend = (f'<div class="month-spark">{spark}'
             f'<span class="et-prev">Lift over base, {labels[0]} → {labels[-1]}</span>'
             f'</div>') if spark else ""
    return f'{trend}<div class="et-table">{head}{body}</div>'


def version_table_html(groups: list, overall_rate: float | None) -> str:
    """Model versions grouped by market family — did the change actually help?

    ``groups`` = the output of ``web.analytics._version_groups``. Each family shows its
    live version expanded with **the change against the version it replaced**, and
    everything earlier collapsed into one line: fourteen version rows is a wall, and the
    question a reader has is "did this market get better", not "list everything ever
    stamped".

    **The comparison column is allowed to say no.** A version that lost ground shows a
    negative, and one whose predecessor has too small a sample says so instead of showing
    a number — a model page that renders every update as an improvement is not a model
    page. The change is measured in *lift over each version's own base rate*, never in
    hit rate: versions move thresholds, so two versions of one market can face different
    base rates, and a raw-rate comparison would read that as a quality change.

    Retired markets render in their own section on the rare occasions they appear at all.
    Performance shows what was *served*, and both retired markets were retired precisely
    because they could not clear the curation floor — total bases reached 70+ once in
    2,204 props, walks three times in 98 — so the cohort filter removes them upstream
    almost every time. The section exists so that when a row does survive, its record is
    not read as an old engine underperforming: the market was unservable, not the scorer.
    """
    if not groups:
        return '<div class="mlb-empty">No versioned props yet.</div>'

    def change_cell(group):
        change = group.get("change_vs_previous")
        if change is None:
            return ('<span class="et-prev">'
                    + escape(group.get("comparison_note") or "no predecessor")
                    + '</span>')
        pp = change * 100
        cls = "pos" if pp >= 1 else "neg" if pp <= -1 else "flat"
        word = ("better than" if pp >= 1 else "behind" if pp <= -1 else "level with")
        badge = ('<span class="cal-small">Small sample</span>'
                 if group.get("comparison_small") else "")
        return (f'<b class="cal-diff {cls}">{"+" if pp >= 0 else ""}{pp:.1f} pts</b>'
                f'<span class="et-prev"> {word} {escape(str(group["previous_version"]))}'
                f'</span>{badge}')

    def line(item, css, change=""):
        t = item["tally"]
        return (f'<div class="ver-row {css}">'
                f'<span class="et-seg">{escape(str(item["version"]))}</span>'
                f'<span class="ds-sub">{escape(item["first"])}→{escape(item["last"])}</span>'
                f'<span>{t["hit"]}–{t["miss"]}</span>'
                f'<span class="cal-rate">{_rate(t)} '
                f'<span class="ds-sub">n={t["hit"] + t["miss"]:,}</span></span>'
                f'<span>{_lift_html(t["hit_rate"], item.get("base"))}</span>'
                f'<span>{change}</span></div>')

    head = ('<div class="ver-row et-head"><span>Version</span><span>Active</span>'
            '<span>Record</span><span>Hit rate</span><span>vs base</span>'
            '<span>vs previous version</span></div>')

    live, retired = [], []
    for group in groups:
        block = [f'<div class="ver-group-label">{escape(group["label"])}</div>']
        if group["current"]:
            block.append(line(group["current"], "ver-current", change_cell(group)))
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
                f'<span class="ds-sub">n={t["hit"] + t["miss"]:,}</span></span>'
                f'<span>{_lift_html(t["hit_rate"], group.get("earlier_base"))}</span>'
                f'<span></span></div>')
        (retired if group["retired"] else live).append("".join(block))

    out = f'<div class="et-table ver-table">{head}{"".join(live)}</div>'
    if retired:
        out += ('<div class="ver-retired-head">Retired markets</div>'
                f'<div class="et-table ver-table">{"".join(retired)}</div>'
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


def signal_check_html(items: list[dict]) -> str:
    """The page's executive summary: two or three labelled observations, not one sentence.

    ``items`` come from ``services.model_trust.signal_check``, which decides *what* is worth
    saying; this only renders it. Every clause narrates a figure computed elsewhere on the
    page — the coverage table, the direction lift, the period-over-period trend — so the
    summary can never disagree with the evidence below it.
    """
    if not items:
        return ""
    rows = []
    for item in items:
        subject = (f'<strong>{escape(str(item["subject"]))}</strong> '
                   if item.get("subject") else "")
        rows.append(f'<div class="sc-item"><span class="sc-label">'
                    f'{escape(str(item["label"]))}</span>'
                    f'<p class="sc-text">{subject}{escape(str(item["text"]))}</p></div>')
    return ('<section class="signal-check" aria-label="Signal check">'
            '<div class="sc-head">Signal check</div>'
            f'{"".join(rows)}</section>')


def performance_summary_html(overall: dict, overall_lift: float | None,
                             prior: dict, prior_lift: float | None, prior_label: str,
                             *, avg_score: float | None = None, slates: int | None = None,
                             period_label: str = "", cohort: str = "",
                             base_rate: float | None = None) -> str:
    """Hit rate, lift over baseline and sample as three equal primary figures.

    **Baseline-adjusted performance is deliberately the same size as the raw hit rate.**
    The previous headline led with 63.1% and a record, which is the figure most likely to
    be read as skill and least likely to be it: 1+ hit — 61% of everything served — has a
    61% base rate. Putting the two side by side is the smallest change that stops the page
    flattering the model.
    """
    decided = overall["hit"] + overall["miss"]
    rate = f'{overall["hit_rate"]:.1%}' if overall["hit_rate"] is not None else "—"
    lift_cls = ("pos" if overall_lift > 0 else "neg") if overall_lift else "flat"
    lift_text = _pts(overall_lift) if overall_lift is not None else "—"
    base_sub = f"vs {base_rate:.0%} base" if base_rate is not None else "no base measured"
    tiles = [
        ("Hit rate", rate, f"{overall['hit']}–{overall['miss']} record", ""),
        ("vs baseline", lift_text, base_sub, lift_cls),
        ("Graded", f"{decided:,}", (f"{slates} slate{'s' if slates != 1 else ''}"
                                    if slates is not None else ""), ""),
    ]
    cells = "".join(
        f'<div class="ps-tile"><div class="ps-label">{escape(label)}</div>'
        f'<div class="ps-value {cls}">{value}</div>'
        f'<div class="ps-sub">{escape(sub)}</div></div>'
        for label, value, sub, cls in tiles)

    meta = []
    if period_label or cohort:
        meta.append(escape(" · ".join(part for part in (period_label, cohort) if part)))
    prior_rate = prior.get("hit_rate")
    prior_decided = prior["hit"] + prior["miss"]
    if prior_rate is not None and prior_decided:
        trend = ""
        if overall["hit_rate"] is not None:
            delta = (overall["hit_rate"] - prior_rate) * 100
            cls = "pos" if delta >= 0 else "neg"
            trend = (f' <span class="cal-diff {cls}">{"+" if delta >= 0 else ""}'
                     f'{delta:.1f} pts</span>')
        prior_lift_text = (f' ({_pts(prior_lift)} over base)'
                           if prior_lift is not None else "")
        meta.append(f'{escape(prior_label)}: {prior_rate:.1%}{prior_lift_text}{trend}')
    if overall["void"] or overall["pending"]:
        meta.append(f'{overall["void"]} void · {overall["pending"]} pending')
    if avg_score is not None:
        meta.append(f"avg score {avg_score:.0f}")
    return (f'<div class="perf-summary">{cells}</div>'
            f'<div class="ps-meta">{" · ".join(meta)}</div>')


def trust_board_html(groups: list[dict]) -> str:
    """Markets sorted into trust tiers — the page's verdict, stated before its evidence.

    ``groups`` come from ``services.model_trust.trust_tiers``; empty tiers never reach
    here, because an empty "Strong signal" heading reads as a finding when it is usually
    just missing data. Every chip carries its lift and its sample, so a tier can be
    checked against the tables below rather than taken on faith.
    """
    if not groups:
        return ""
    blocks = []
    for group in groups:
        chips = "".join(
            f'<li class="tb-chip"><span class="tb-market">{escape(str(m["label"]))}</span>'
            f'<span class="tb-lift">{_pts(m["lift"]) if m["lift"] is not None else "—"}'
            f'<span class="et-prev"> n={m["n"]:,}</span></span>'
            + (f'<span class="tb-note">{escape(m["note"])}</span>' if m["note"] else "")
            + '</li>'
            for m in group["markets"])
        blocks.append(
            f'<div class="tb-tier tb-{escape(group["key"])}">'
            f'<div class="tb-tier-head">{escape(group["label"])}</div>'
            f'<div class="tb-blurb">{escape(group["blurb"])}</div>'
            f'<ul class="tb-list">{chips}</ul></div>')
    return f'<div class="trust-board">{"".join(blocks)}</div>'


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


_STARVED_LIFT = 0.05    # beats its own base rate by this much...
_STARVED_SHARE = 0.10   # ...yet under this share of it ever clears the floor


def starved_basis(item: dict) -> tuple[int, int, float | None]:
    """``(recorded, served, lift)`` the starvation test is judged on.

    The **current engine's** own record where the caller supplies it, else everything
    recorded. Serving share is a fact about the scorer running today, not about every
    scorer a market has ever had: pooled across versions, `batter-k-v1`'s 3.7% share
    held the flag on `batter-k-v2` months after the fix that took it to 17.7% and
    +33.8 over base on what it serves. Falls back to the pooled figures so callers
    predating `live_n` (and markets with no current engine at all) still work.
    """
    if item.get("live_n"):
        return item["live_n"], item.get("live_served_n") or 0, item.get("live_lift")
    return item.get("recorded_n") or 0, item.get("served_n") or 0, item.get("recorded_lift")


def is_starved(item: dict) -> bool:
    """Good but unservable: real edge, almost never offered. One definition, so the
    coverage table and the takeaway sentence can never disagree about a market."""
    recorded, served, lift = starved_basis(item)
    if not recorded or lift is None:
        return False
    return lift >= _STARVED_LIFT and served / recorded < _STARVED_SHARE


def market_coverage_html(coverage: list[dict], floor: int) -> str:
    """Every market's measured edge, ranked by it — the page's "what's working" table.

    **Edge over base rate is the primary column, and hit rate is deliberately quieter.**
    The question this page answers is whether the model beats what would happen without
    it, and raw conversion cannot answer that: `batter_hit` converts 66% against a 61%
    base, WNBA assists convert 62% against a 33% one. Ranked on hit rate those come out
    in the opposite order, which is how this table used to read.

    **The blind spot it also closes.** Every other table on this page reads *served* props,
    so a market that is genuinely good but never clears the curation floor is invisible by
    construction — indistinguishable from a market that is bad. `batter_k` carries one of
    the highest lifts of any market and had been served six times, because its scorer
    topped out at 75 against a floor of 70. It was found by accident. So the edge cell
    carries both figures: what the served props did, and what everything predicted did.

    ``coverage`` rows: label, recorded (n, lift, hit_rate), served (n, lift, hit_rate).
    """
    if not coverage:
        return '<div class="mlb-empty">No graded predictions to summarise.</div>'

    def tone(lift):
        # Near-zero stays neutral: colouring a +0.4 green claims an edge the number does
        # not carry, and this page is read for exactly that distinction.
        if lift is None:
            return "flat"
        return "pos" if lift >= 0.02 else "neg" if lift <= -0.02 else "flat"

    head = ('<div class="mc-row mc-head"><span>Market<small>ranked by edge</small></span>'
            '<span>Edge vs base<small>served · all predictions</small></span>'
            '<span>Hit rate<small>served</small></span>'
            '<span>N<small>served</small></span>'
            f'<span>Share served<small>cleared {floor}+</small></span></div>')
    body = []
    for item in coverage:
        # The displayed share stays pooled across versions — it is the market's whole
        # recorded history, which is what the "all predictions" figure reports too.
        share = item["served_n"] / item["recorded_n"] if item["recorded_n"] else 0.0
        # Good and starved: the market earns its place but the scale cannot reach the
        # floor, so almost none of it is ever offered. That is a scoring problem wearing
        # a market's clothes, and it reads as "this market is bad" everywhere else.
        flag = '<span class="mc-flag">Starved</span>' if is_starved(item) else ""
        served_lift, served_n = item.get("served_lift"), item.get("served_n") or 0
        small = ('<span class="cal-small">Small</span>'
                 if 0 < served_n < 30 else "")
        edge = (f'<b class="mc-edge {tone(served_lift)}">{_pts(served_lift)}</b>'
                if served_lift is not None else '<b class="mc-edge flat">—</b>')
        all_edge = (f'<span class="et-prev">all {_pts(item["recorded_lift"])}'
                    f' · n={item["recorded_n"]:,}</span>'
                    if item.get("recorded_lift") is not None else
                    f'<span class="et-prev">n={item["recorded_n"]:,} recorded</span>')
        served_rate = item.get("served_hit_rate")
        rate_cell = (f'{served_rate:.1%}' if served_rate is not None else "—")
        base = item.get("served_base")
        base_sub = f'<span class="et-prev"> base {base:.0%}</span>' if base is not None else ""
        # A market under the minimum sample is sorted last *and* quieted. Sorting alone
        # was not enough: `batter_k`'s +41.8 stayed the largest, greenest number in the
        # table while sitting at the bottom, which reads as a broken ranking rather than
        # as an unmeasured market.
        body.append(
            f'<div class="mc-row{" mc-row-small" if small else ""}">'
            f'<span class="et-seg">{escape(item["label"])}{flag}</span>'
            f'<span class="mc-edge-cell">{edge}{all_edge}</span>'
            f'<span class="cal-rate">{rate_cell}{base_sub}</span>'
            f'<span class="mc-n">{served_n:,}{small}</span>'
            f'<span class="mc-share">{share:.0%}</span></div>')
    note = ('<div class="mtp-legend"><span>Edge is the served props\u2019 hit rate minus the '
            'rate that event happens on its own; \u201call\u201d is the same figure over '
            'everything the market predicted, floor or not. \u201cStarved\u201d means the '
            'market beats its base rate by 5+ points across everything it predicted, yet '
            'under a tenth of those ever clear the floor \u2014 the scale cannot reach, so '
            'the edge is never offered. Judged on the engine running today: a superseded '
            'scorer\u2019s serving share is not a fact about the current one.</span></div>')
    return f'<div class="mc-table">{head}{"".join(body)}</div>{note}'
