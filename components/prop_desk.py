"""Render the postseason prop desk (pure HTML; every number arrives precomputed).

**One layout, six modes.** Starters, then the two lineups, then thresholds — always in that
order. A mode changes only *which* cells are visible and which rows are emphasised, through
``data-m`` attributes and one ``data-mode`` on the section, so a reader learns the page once.
Without the script the controls stay hidden and the page shows the Hits view.

**No verdicts in the markup.** No colour means good or bad here: evidence is neutral text,
playoff games carry the accent, and small samples are muted. There are no scores, no
"strong", no "best". (Decision log 2026-09-30.)
"""

from __future__ import annotations

from html import escape

from services.mlb_prop_desk import (
    HITTER_THRESHOLDS, MODES, SMALL, Count, Hitter, HitterSlice, PropDesk, Side, Starter,
)

_HITTER_ALL = "hits tb bk"
_STARTER_ALL = "sk ha bb"


def _e(value) -> str:
    return escape(str(value))


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _pct(count: Count | None) -> str:
    """A per-PA rate, always with its sample: "24% · 122/510"."""
    if count is None or not count.n:
        return "—"
    return f"{round(100 * count.hit / count.n)}% <small>{count.hit}/{count.n}</small>"


def _strip(values: tuple[int, ...], post: tuple[bool, ...] = ()) -> str:
    """Game-by-game values, oldest first. Playoff games are set apart by the accent."""
    if not values:
        return '<span class="pd-strip-empty">—</span>'
    cells = []
    for i, v in enumerate(values):
        cls = "pd-v post" if (i < len(post) and post[i]) else "pd-v"
        cells.append(f'<span class="{cls}">{v}</span>')
    return f'<span class="pd-strip" aria-label="Oldest to newest">{"".join(cells)}</span>'


# --- starters --------------------------------------------------------------------------

_STARTER_ROWS = (
    # key, label, modes that emphasise it, workload?
    ("pitches", "Pitches", _STARTER_ALL, True),
    ("bf", "Batters faced", _STARTER_ALL, True),
    ("ip", "Innings", _STARTER_ALL, True),
    ("k", "Strikeouts", "sk bk", False),
    ("h", "Hits allowed", "ha", False),
    ("bb", "Walks", "bb", False),
)


def _avg_cell(sp: Starter, key: str) -> str:
    if key == "ip":
        outs = sp.avg.get("outs", 0.0)
        return f"{int(outs // 3)}.{int(round(outs % 3))}"
    return f"{sp.avg.get(key, 0):g}"


def _outing_value(o, key: str) -> str:
    return o.ip if key == "ip" else str(getattr(o, key))


def starter_card(sp: Starter | None, side: Side, facing: Side) -> str:
    if sp is None:
        return (f'<div class="pd-sp pd-sp--none"><div class="pd-sp-head"><strong>'
                f'{_e(side.short)} starter</strong></div><p class="pd-quiet">No probable '
                "starter matched in the feed, so there is nothing to show.</p></div>")
    outings = list(sp.recent) + list(sp.post)
    head = "".join(
        f'<th class="{"post" if i >= len(sp.recent) else ""}" scope="col">'
        f'{_e(o.day)}{"" if o.start else "<small>relief</small>"}</th>'
        for i, o in enumerate(outings))
    rows = []
    for key, label, emph, workload in _STARTER_ROWS:
        cells = "".join(
            f'<td class="{"post" if i >= len(sp.recent) else ""}">{_e(_outing_value(o, key))}</td>'
            for i, o in enumerate(outings))
        rows.append(f'<tr class="pd-sp-row{" workload" if workload else ""}" data-emph="{emph}">'
                    f'<th scope="row">{label}</th><td class="pd-avg">{_avg_cell(sp, key)}</td>'
                    f'{cells}</tr>')
    divider = (' · <span class="pd-post-key">playoff</span>' if sp.post else "")
    post_note = ("" if sp.post else
                 '<p class="pd-quiet">No postseason appearance yet.</p>')
    vs = ""
    if sp.vs_opp:
        bits = "; ".join(f"{o.day}: {o.ip} IP, {o.k} K, {o.h} H, {o.bb} BB" for o in sp.vs_opp)
        vs = (f'<p class="pd-quiet pd-small-sample">vs {_e(facing.short)} this season '
              f'({len(sp.vs_opp)} {"start" if len(sp.vs_opp) == 1 else "starts"}): {_e(bits)}</p>')
    lineup = ""
    if sp.lineup:
        state = "confirmed" if facing.confirmed else "last game's"
        lineup = (
            f'<div class="pd-sp-lineup"><span class="pd-label">{_e(facing.short)} '
            f'{state} lineup vs {_e(sp.throws)}</span>'
            f'<span data-m="sk bk">K {_pct(sp.lineup.get("k"))}</span>'
            f'<span data-m="ha hits tb">Hit {_pct(sp.lineup.get("h"))}</span>'
            f'<span data-m="bb">BB {_pct(sp.lineup.get("bb"))}</span>'
            f'<span class="pd-quiet">per PA · {_e(sp.lineup_note)}</span></div>')
    return (
        f'<div class="pd-sp" data-sp="{_e(sp.pid)}">'
        f'<div class="pd-sp-head"><strong>{_e(sp.name)}</strong>'
        f'<span>{_e(sp.throws)} · {_e(side.short)} vs {_e(facing.short)} · '
        f'{sp.starts} regular-season starts</span></div>'
        f'<div class="pd-sp-scroll"><table class="pd-sp-table">'
        f'<thead><tr><th></th><th scope="col">Avg</th>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        f'<p class="pd-quiet">Last {len(sp.recent)} regular-season starts, oldest first{divider}. '
        f'Innings are outs recorded ÷ 3.</p>'
        f'{post_note}{lineup}{vs}</div>')


# --- hitters ---------------------------------------------------------------------------

def _summary(h: Hitter, facing: Starter | None) -> str:
    """The one-line read for the selected mode: season, then L14, then postseason."""
    season, l14, post = (h.slices.get(k) for k in ("season", "l14", "post"))

    def trio(column: str, at_least: int, label: str) -> str:
        bits = [f"<b>{label} {season.clears(column, at_least).text}</b>" if season else ""]
        if l14:
            bits.append(f"L14 {l14.clears(column, at_least).text}")
        if post and post.games:
            bits.append(f'<span class="pd-post-key">Post {post.clears(column, at_least).text}</span>')
        return " · ".join(b for b in bits if b)

    k_season = Count(season.k, season.pa) if season else None
    bb_season = Count(season.bb, season.pa) if season else None
    hand = facing.throws if facing else "SP"
    return (
        f'<span class="pd-sum" data-m="hits">{trio("h", 1, "1+ H")}</span>'
        f'<span class="pd-sum" data-m="tb">{trio("tb", 2, "2+ TB")}</span>'
        f'<span class="pd-sum" data-m="bk sk"><b>K {_pct(k_season)}</b> · vs {_e(hand)} '
        f'{_pct(h.vs_hand)}</span>'
        f'<span class="pd-sum" data-m="ha">{trio("h", 1, "1+ H")}</span>'
        f'<span class="pd-sum" data-m="bb"><b>BB {_pct(bb_season)}</b></span>')


def _strips(h: Hitter) -> str:
    return (
        f'<span data-m="hits ha">{_strip(h.strip.get("h", ()), h.strip_post)}</span>'
        f'<span data-m="tb">{_strip(h.strip.get("tb", ()), h.strip_post)}</span>'
        f'<span data-m="bk sk">{_strip(h.strip.get("k", ()), h.strip_post)}</span>'
        f'<span data-m="bb">{_strip(h.strip.get("bb", ()), h.strip_post)}</span>')


# Columns of the expanded table: label, cell function, modes that show it.
def _cols():
    def c(col, n):
        return lambda s: s.clears(col, n).text
    return (
        ("1+ H", c("h", 1), "hits ha"), ("2+ H", c("h", 2), "hits"),
        ("2+ TB", c("tb", 2), "tb"), ("3+ TB", c("tb", 3), "tb"), ("4+ TB", c("tb", 4), "tb"),
        ("TB", lambda s: str(s.tb), "tb"), ("XBH", lambda s: str(s.xbh), "tb"),
        ("K", lambda s: str(s.k), "bk"),
        ("K/PA", lambda s: _pct(Count(s.k, s.pa)), "bk sk"),
        ("1+ K", c("k", 1), "bk sk"), ("2+ K", c("k", 2), "bk"),
        ("BB", lambda s: str(s.bb), "bb"),
        ("BB/PA", lambda s: _pct(Count(s.bb, s.pa)), "bb"),
    )


_SLICE_CLASS = {"season": "base", "l28": "recent", "l14": "recent",
                "post": "small", "series": "small", "opp": "small"}


def _detail(h: Hitter, facing: Starter | None) -> str:
    opp = []
    if h.slot:
        opp.append(f"Bats {_ordinal(h.slot)}")
    if h.pa_per_game:
        opp.append(f"{h.pa_per_game:g} PA per start this season")
    if h.slot_pa:
        opp.append(f"league average from the {_ordinal(h.slot)} spot: {h.slot_pa:g}")
    cols = _cols()
    head = "".join(f'<th scope="col" data-m="{m}">{_e(label)}</th>' for label, _, m in cols)
    rows = []
    for key in ("season", "l28", "l14", "post", "series", "opp"):
        s: HitterSlice | None = h.slices.get(key)
        if s is None:
            continue
        cells = "".join(f'<td data-m="{m}">{fn(s) if s.games else "—"}</td>'
                        for _, fn, m in cols)
        rows.append(
            f'<tr class="pd-slice {_SLICE_CLASS[key]}">'
            f'<th scope="row">{_e(s.label)}<small>{_e(s.span)}</small></th>'
            f'<td>{s.games}</td><td class="pd-line">{f"{s.h}-for-{s.ab}" if s.games else "—"}</td>'
            f'{cells}</tr>')
    bvp = ""
    if facing is not None:
        bvp = (f'<p class="pd-bvp">vs {_e(facing.name)}: {_e(h.bvp_line)}'
               f'<small> — raw counts; too few to mean much</small></p>')
    return (
        f'<div class="pd-detail">'
        f'<p class="pd-opp">{_e(" · ".join(opp)) or "No regular-season starts in the feed"}</p>'
        f'<div class="pd-detail-scroll"><table class="pd-detail-table">'
        f'<thead><tr><th></th><th scope="col">G</th><th scope="col">H-AB</th>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>{bvp}</div>')


def _hitter_row(h: Hitter, facing: Starter | None, confirmed: bool) -> str:
    vs = f" vs {facing.throws}" if facing else ""
    slot = str(h.slot) if h.slot else "–"
    return (
        f'<details class="pd-hitter{"" if confirmed else " unconfirmed"}">'
        f'<summary><span class="pd-slot" aria-label="Batting {_e(slot)}">{_e(slot)}</span>'
        f'<span class="pd-who"><b>{_e(h.name)}</b><small>Bats {_e(h.bats)}{_e(vs)}</small></span>'
        f'<span class="pd-read">{_summary(h, facing)}{_strips(h)}</span></summary>'
        f'{_detail(h, facing)}</details>')


def _lineup(side: Side, facing: Starter | None) -> str:
    badge = ("Confirmed" if side.confirmed else "Not confirmed")
    facing_note = (f'<span class="pd-facing" data-m="bk sk">Facing {_e(facing.throws)} '
                   f'{_e(facing.name)}</span>' if facing else "")
    rows = "".join(_hitter_row(h, facing, side.confirmed) for h in side.hitters)
    if not rows:
        rows = '<p class="pd-quiet">No lineup in the feed for this club.</p>'
    return (
        f'<div class="pd-lineup">'
        f'<div class="pd-lineup-head"><strong>{_e(side.short)}</strong>'
        f'<span class="pd-badge{" off" if not side.confirmed else ""}">{badge}</span>'
        f'{facing_note}</div>'
        f'{"" if side.confirmed else f"<p class=pd-unconfirmed>{_e(side.source)}</p>"}'
        f'{rows}</div>')


# --- thresholds -----------------------------------------------------------------------

def _hitter_thresholds(desk: PropDesk) -> str:
    out = []
    for mode, rows in HITTER_THRESHOLDS.items():
        for i, (label, col, n) in enumerate(rows):
            body = []
            for side in (desk.away, desk.home):
                body.append(f'<tr class="pd-th-team"><th colspan="5">{_e(side.short)}</th></tr>')
                for h in side.hitters:
                    cells = "".join(
                        f'<td class="{"small" if k in ("post",) else ""}">'
                        f'{h.slices[k].clears(col, n).text if h.slices.get(k) and h.slices[k].games else "—"}</td>'
                        for k in ("season", "l28", "l14", "post"))
                    body.append(f'<tr><th scope="row"><span class="pd-slot sm">{h.slot or "–"}</span>'
                                f'{_e(h.name)}</th>{cells}</tr>')
            out.append(
                f'<div class="pd-th-table" data-m="{mode}" data-t="{mode}-{i}"'
                f'{"" if i == 0 else " hidden"}>'
                f'<table><thead><tr><th scope="col">{_e(label)} — games cleared</th>'
                f'<th scope="col">Season</th><th scope="col">L28</th><th scope="col">L14</th>'
                f'<th scope="col">Post</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>')
    return "".join(out)


def _starter_thresholds(desk: PropDesk) -> str:
    out = []
    for mode in ("sk", "ha", "bb"):
        tables = []
        for sp in desk.starters:
            rows = "".join(
                f'<tr><th scope="row">{_e(label)}</th><td>{season.text}</td>'
                f'<td>{recent.text}</td><td class="small">{post.text}</td></tr>'
                for label, season, recent, post in sp.thresholds.get(mode, ()))
            tables.append(
                f'<table><thead><tr><th scope="col">{_e(sp.name)}</th><th scope="col">Season</th>'
                f'<th scope="col">Last {len(sp.recent)}</th><th scope="col">Post</th></tr></thead>'
                f'<tbody>{rows}</tbody></table>')
        out.append(f'<div class="pd-th-table pd-th-starters" data-m="{mode}">{"".join(tables)}</div>')
    return "".join(out)


def _threshold_pills() -> str:
    pills = []
    for mode, rows in HITTER_THRESHOLDS.items():
        buttons = "".join(
            f'<button type="button" data-t="{mode}-{i}" aria-pressed="{"true" if i == 0 else "false"}">'
            f'{_e(label)}</button>' for i, (label, _, _) in enumerate(rows))
        pills.append(f'<div class="pd-tpills" data-m="{mode}" data-pd-tpills hidden>{buttons}</div>')
    return "".join(pills)


# --- the section ----------------------------------------------------------------------

def prop_desk_html(desk: PropDesk | None) -> str:
    if desk is None:
        return ""
    through = desk.data_through.strftime("%b %-d") if desk.data_through else "—"
    reg_end = desk.reg_end.strftime("%b %-d") if desk.reg_end else "—"
    modes = "".join(
        f'<button type="button" data-mode="{key}" aria-pressed="{"true" if key == "hits" else "false"}">'
        f'{_e(label)}</button>' for key, label in MODES)
    notes = "".join(f'<p class="pd-note" data-m="{key}">{_e(text)}</p>'
                    for key, text in desk.notes.items())
    starters = (starter_card(desk.away.starter, desk.away, desk.home)
                + starter_card(desk.home.starter, desk.home, desk.away))
    lineups = (_lineup(desk.away, desk.home.starter) + _lineup(desk.home, desk.away.starter))
    return (
        f'<section class="pd" data-pd data-mode="hits" aria-labelledby="pd-title">'
        f'<div class="pd-head"><h2 id="pd-title">Playoff Prop Desk</h2>'
        f'<span class="pd-through">Data through {_e(through)} · regular season ended '
        f'{_e(reg_end)}</span></div>'
        f'<div class="pd-modes" role="group" aria-label="Market" data-pd-modes hidden>{modes}</div>'
        f'{notes}'
        f'<div class="pd-starters">{starters}</div>'
        f'<div class="pd-lineups">{lineups}</div>'
        f'<div class="pd-thresholds"><div class="pd-th-head"><h3>Thresholds</h3>'
        f'<span class="pd-quiet">Games that cleared each mark. Counts first; a rate only from '
        f'{SMALL} games up. L14/L28 are the last days of the regular season.</span></div>'
        f'{_threshold_pills()}{_hitter_thresholds(desk)}{_starter_thresholds(desk)}</div>'
        f'<p class="pd-legend"><span class="pd-v post">2</span> playoff game · '
        f'strips run oldest → newest · tap a hitter for the full breakdown. Evidence, not '
        f'picks: no odds are read and nothing here is scored.</p>'
        f'</section>')
