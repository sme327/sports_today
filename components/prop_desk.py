"""Render the postseason prop desk (pure HTML; every number arrives precomputed).

**One layout, six modes.** Starters, then the two lineups, then thresholds — always in that
order. A mode changes only *which* cells are visible and which are emphasised, through
``data-m`` attributes and one ``data-mode`` on the section, so a reader learns the page once.
Without the script the controls stay hidden and the page shows the Hits view.

**Collapsed is a scan, expanded is an investigation.** A hitter row shows the slot, the name,
the hand, three counts (Season · L14 · Post) and a game strip; everything else — L28,
plate appearances, the opponent, the series, batter-vs-pitcher — waits behind a tap. A
starter card leads with one headline stat for the selected market, then workload, then the
recent strip; the start-by-start table is folded away. (Decision log 2026-09-30.)

**No verdicts in the markup.** No colour means good or bad here: evidence is neutral text,
playoff games carry the accent, and small samples are muted. No scores, no "strong", no
"best".
"""

from __future__ import annotations

from html import escape

from services.mlb_prop_desk import (
    HITTER_THRESHOLDS, MODES, SMALL, STARTER_THRESHOLDS, Count, Hitter, HitterSlice, PropDesk,
    Side, Starter,
)

# Reconstructed from play-by-play, not the official box score — marked "~" with a tooltip so
# an estimate never looks identical to an official figure. Batters faced is an exact count.
_APPROX = ("Reconstructed from play-by-play: pitches are summed per plate appearance and "
           "innings are outs recorded ÷ 3. Close to the official box score, not identical.")

# The column each hitter mode counts games on, and its label.
_HITTER_KEY = {"hits": ("h", 1, "1+ H"), "tb": ("tb", 2, "2+ TB"), "bk": ("k", 1, "1+ K")}
# What a starter card leads with in each mode: (stat key, unit).
_HEADLINE = {"sk": ("k", "K / start"), "bk": ("k", "K / start"),
             "ha": ("h", "H allowed / start"), "hits": ("h", "H allowed / start"),
             "tb": ("h", "H allowed / start"), "bb": ("bb", "BB / start")}


def _e(value) -> str:
    return escape(str(value))


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _pct(count: Count | None) -> str:
    """A per-PA rate, always with its sample: "24% · 122/510"."""
    if count is None or not count.n:
        return "—"
    return f"{round(100 * count.hit / count.n)}% <small>{count.hit}/{count.n}</small>"


def _strip(values, post=(), titles=()) -> str:
    """Game-by-game values, oldest first. A rule marks where the regular season stops; the
    playoff games after it are outlined."""
    if not values:
        return '<span class="pd-strip-empty">—</span>'
    cells, crossed = [], False
    for i, v in enumerate(values):
        is_post = i < len(post) and post[i]
        if is_post and not crossed:
            cells.append('<span class="pd-sep" aria-label="postseason begins"></span>')
            crossed = True
        title = f' title="{_e(titles[i])}"' if i < len(titles) and titles[i] else ""
        cells.append(f'<span class="pd-v{" post" if is_post else ""}"{title}>{v}</span>')
    return f'<span class="pd-strip" aria-label="Oldest to newest">{"".join(cells)}</span>'


def _watch(kind: str, key: str, label: str) -> str:
    return (f'<button type="button" class="pd-watch" data-watch="{_e(kind)}:{_e(key)}" '
            f'data-watch-label="{_e(label)}" aria-pressed="false" '
            f'aria-label="Watch {_e(label)}" hidden>☆</button>')


# --- starters --------------------------------------------------------------------------

def _ip(outs: float) -> str:
    return f"{int(outs // 3)}.{int(round(outs % 3))}"


def _start_table(sp: Starter) -> str:
    outings = list(sp.recent) + list(sp.post)
    gaps = sp.gap_before

    def cls(i: int) -> str:
        return " ".join(b for b in ("post" if i >= len(sp.recent) else "",
                                    "gap" if i in gaps else "") if b)

    head = "".join(f'<th class="{cls(i)}" scope="col">{_e(o.day)}'
                   f'{"" if o.start else "<small>relief</small>"}</th>'
                   for i, o in enumerate(outings))
    rows = []
    for key, label in (("pitches", "Pitches ~"), ("bf", "Batters faced"), ("ip", "Innings ~"),
                       ("k", "Strikeouts"), ("h", "Hits allowed"), ("bb", "Walks")):
        cells = "".join(f'<td class="{cls(i)}">{_e(o.ip if key == "ip" else getattr(o, key))}</td>'
                        for i, o in enumerate(outings))
        avg = f"~{_ip(sp.avg['outs'])}" if key == "ip" else (
            f"~{sp.avg[key]:g}" if key == "pitches" else f"{sp.avg[key]:g}")
        name = f'<abbr title="{_e(_APPROX)}">{label}</abbr>' if "~" in label else label
        rows.append(f'<tr><th scope="row">{name}</th><td class="pd-avg">{avg}</td>{cells}</tr>')
    vs = ""
    if sp.vs_opp:
        bits = "; ".join(f"{o.day}: {o.ip} IP, {o.k} K, {o.h} H, {o.bb} BB" for o in sp.vs_opp)
        vs = f'<p class="pd-quiet">vs {_e(sp.opp)} this season: {_e(bits)}</p>'
    return (f'<details class="pd-sp-more"><summary>Start by start</summary>'
            f'<div class="pd-sp-scroll"><table class="pd-sp-table"><thead><tr><th></th>'
            f'<th scope="col">Avg</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
            f'</div>{vs}</details>')


def starter_card(sp: Starter | None, side: Side, facing: Side) -> str:
    if sp is None:
        # Two different absences, worded apart: tomorrow's Game 3 usually has no announced
        # starter yet, which is not the same as a starter the feed has never seen.
        why = (f"{_e(side.probable)} has no plate appearances against him in the feed, so "
               "there is nothing to show." if side.probable else
               "Starter not announced yet. The card fills in once a probable is named and the "
               "page is refreshed.")
        return (f'<div class="pd-sp pd-sp--none"><div class="pd-sp-head"><div><strong>'
                f'{_e(side.short)} starter</strong></div></div>'
                f'<p class="pd-quiet">{why}</p></div>')
    outings = list(sp.recent) + list(sp.post)
    post_flags = [False] * len(sp.recent) + [True] * len(sp.post)
    titles = [f"{o.day} vs {o.opp}" + ("" if o.start else " (relief)") for o in outings]

    headlines = "".join(
        f'<span data-m="{mode}"><b>{sp.avg[key]:g}</b> {unit}</span>'
        for mode, (key, unit) in _HEADLINE.items())
    workload = (f'<abbr title="{_e(_APPROX)}">~{sp.avg["pitches"]:.0f} pitches</abbr> · '
                f'<b>{sp.avg["bf"]:g} BF</b> · '
                f'<abbr title="{_e(_APPROX)}">~{_ip(sp.avg["outs"])} IP</abbr>'
                f'<small> per start · {sp.starts} regular-season starts</small>')
    strips = (
        f'<div class="pd-sp-strip" data-m="sk bk"><span>Recent K</span>'
        f'{_strip([o.k for o in outings], post_flags, titles)}</div>'
        f'<div class="pd-sp-strip" data-m="ha hits tb"><span>Recent H</span>'
        f'{_strip([o.h for o in outings], post_flags, titles)}</div>'
        f'<div class="pd-sp-strip" data-m="bb"><span>Recent BB</span>'
        f'{_strip([o.bb for o in outings], post_flags, titles)}</div>'
        f'<div class="pd-sp-strip pd-sp-work" data-m="sk ha bb"><span>Pitches ~</span>'
        f'{_strip([o.pitches for o in outings], post_flags, titles)}</div>'
        f'<div class="pd-sp-strip pd-sp-work" data-m="sk ha bb"><span>BF</span>'
        f'{_strip([o.bf for o in outings], post_flags, titles)}</div>')
    span = (f'Last {len(sp.recent)} recorded starts'
            + (f' · <b class="pd-span">span {_e(sp.recent_span)}</b>' if sp.recent_span else "")
            + (' · <span class="pd-post-key">playoff</span> after the rule' if sp.post
               else " · no postseason appearance yet"))
    lineup = ""
    if sp.lineup:
        state = "confirmed" if facing.confirmed else "last game's"
        lineup = (
            f'<p class="pd-sp-lineup">{_e(facing.short)} {state} lineup vs {_e(sp.throws)}: '
            f'<span data-m="sk bk">K {_pct(sp.lineup.get("k"))}</span>'
            f'<span data-m="ha hits tb">hits {_pct(sp.lineup.get("h"))}</span>'
            f'<span data-m="bb">BB {_pct(sp.lineup.get("bb"))}</span> per PA</p>')
    return (
        f'<div class="pd-sp" id="pd-sp-{_e(sp.pid)}">'
        f'<div class="pd-sp-head"><div><strong>{_e(sp.name)}</strong>'
        f'<span>{_e(sp.throws)} · {_e(side.short)} vs {_e(facing.short)}</span></div>'
        f'{_watch("sp", sp.pid, sp.name)}</div>'
        f'<div class="pd-sp-headline">{headlines}</div>'
        f'<div class="pd-sp-workload">{workload}</div>'
        f'{strips}<p class="pd-quiet">{span}</p>{lineup}{_start_table(sp)}</div>')


# --- hitters ---------------------------------------------------------------------------

def _count_cells(h: Hitter, column: str, at_least: int) -> str:
    out = []
    for key, label in (("season", "Season"), ("l14", "L14"), ("post", "Post")):
        s = h.slices.get(key)
        if s is None or (key == "post" and not s.games):
            continue
        cls = " post" if key == "post" else ""
        # Bare counts on the collapsed row (the scan); rates live in the expansion and the
        # threshold table, where there is room to put the sample beside them.
        count = s.clears(column, at_least)
        out.append(f'<span class="pd-c{cls}"><small>{label}</small>{count.hit}/{count.n}</span>')
    return "".join(out)


def _summary(h: Hitter, facing: Starter | None) -> str:
    """Season · L14 · Post for the mode's own count. Nothing else on a collapsed row."""
    cells = "".join(
        f'<span class="pd-sum" data-m="{mode}{" ha" if mode == "hits" else ""}">'
        f'{_count_cells(h, col, n)}</span>'
        for mode, (col, n, label) in _HITTER_KEY.items())
    hand = facing.throws if facing else "SP"
    season = h.slices.get("season")
    k_rate = Count(season.k, season.pa) if season else None
    bb_rate = Count(season.bb, season.pa) if season else None
    cells += (f'<span class="pd-sum" data-m="sk">'
              f'<span class="pd-c"><small>Season</small>{_pct(k_rate)}</span>'
              f'<span class="pd-c"><small>vs {_e(hand)}</small>{_pct(h.vs_hand)}</span></span>'
              f'<span class="pd-sum" data-m="bb">'
              f'<span class="pd-c"><small>Season</small>{_pct(bb_rate)}</span></span>')
    # Batter K also wants the rate against tonight's hand, beside the game counts.
    cells += (f'<span class="pd-sum pd-sum-extra" data-m="bk"><span class="pd-c">'
              f'<small>K% vs {_e(hand)}</small>{_pct(h.vs_hand)}</span></span>')
    return cells


def _strips(h: Hitter) -> str:
    return "".join(
        f'<span class="pd-row-strip" data-m="{m}">{_strip(h.strip.get(c, ()), h.strip_post)}</span>'
        for c, m in (("h", "hits ha"), ("tb", "tb"), ("k", "bk sk"), ("bb", "bb")))


def _cols():
    def c(col, n):
        return lambda s: s.clears(col, n).text
    return (
        ("1+ H", c("h", 1), "hits ha"), ("2+ H", c("h", 2), "hits"),
        ("TB", lambda s: str(s.tb), "tb"), ("2+ TB", c("tb", 2), "tb"),
        ("3+ TB", c("tb", 3), "tb"), ("4+ TB", c("tb", 4), "tb"),
        ("XBH", lambda s: str(s.xbh), "tb"),
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
        cells = "".join(f'<td data-m="{m}">{fn(s) if s.games else "—"}</td>' for _, fn, m in cols)
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


_HANDS = {"L": "LHB", "R": "RHB", "S": "Switch"}


def _hitter_row(h: Hitter, facing: Starter | None, confirmed: bool) -> str:
    slot = str(h.slot) if h.slot else "–"
    vs = f" vs {facing.throws}" if facing else ""
    return (
        f'<details class="pd-hitter{"" if confirmed else " unconfirmed"}" id="pd-h-{_e(h.pid)}">'
        f'<summary><span class="pd-slot" aria-label="Batting {_e(slot)}">{_e(slot)}</span>'
        f'<span class="pd-who"><b>{_e(h.name)}</b>'
        f'<small>{_e(_HANDS.get(h.hand or "", "—"))}{_e(vs)}</small></span>'
        f'<span class="pd-read">{_summary(h, facing)}</span>'
        f'{_strips(h)}{_watch("h", h.pid, h.name)}</summary>'
        f'{_detail(h, facing)}</details>')


def _lineup(side: Side, facing: Starter | None) -> str:
    badge = ("✓ Confirmed lineup" if side.confirmed else "Not confirmed")
    facing_note = (f'<span class="pd-facing">vs {_e(facing.throws)} {_e(facing.name)}</span>'
                   if facing else "")
    # What the row counts, said once per lineup rather than on all nine rows.
    key = "".join(f'<span class="pd-lineup-key" data-m="{m}">{_e(text)}</span>' for m, text in (
        ("hits ha", "Games with 1+ hit"), ("tb", "Games with 2+ total bases"),
        ("bk", "Games with 1+ strikeout"), ("sk", "Strikeouts per PA"),
        ("bb", "Walks per PA")))
    rows = "".join(_hitter_row(h, facing, side.confirmed) for h in side.hitters)
    if not rows:
        rows = '<p class="pd-quiet">No lineup in the feed for this club.</p>'
    return (
        f'<div class="pd-lineup">'
        f'<div class="pd-lineup-head"><strong>{_e(side.short)}</strong>'
        f'<span class="pd-badge{" off" if not side.confirmed else ""}">{badge}</span>'
        f'{facing_note}{key}</div>'
        f'{"" if side.confirmed else f"<p class=pd-unconfirmed>{_e(side.source)}</p>"}'
        f'{rows}</div>')


# --- thresholds: a lookup, one table at a time ------------------------------------------

def _pills(mode: str, labels) -> str:
    buttons = "".join(
        f'<button type="button" data-t="{mode}-{i}" aria-pressed="{"true" if i == 0 else "false"}">'
        f'{_e(label)}</button>' for i, label in enumerate(labels))
    return f'<div class="pd-tpills" data-m="{mode}" data-pd-tpills hidden>{buttons}</div>'


def _hitter_thresholds(desk: PropDesk) -> str:
    out = []
    for mode, rows in HITTER_THRESHOLDS.items():
        out.append(_pills(mode, [label for label, _, _ in rows]))
        for i, (label, col, n) in enumerate(rows):
            body = []
            for side in (desk.away, desk.home):
                body.append(f'<tr class="pd-th-team"><th colspan="4">{_e(side.short)}</th></tr>')
                for h in side.hitters:
                    cells = "".join(
                        f'<td class="{"post" if k == "post" else ""}">'
                        f'{h.slices[k].clears(col, n).text if h.slices.get(k) and h.slices[k].games else "—"}</td>'
                        for k in ("season", "l14", "post"))
                    body.append(f'<tr><th scope="row"><span class="pd-slot sm">{h.slot or "–"}</span>'
                                f'{_e(h.name)}</th>{cells}</tr>')
            out.append(
                f'<div class="pd-th-table" data-m="{mode}" data-t="{mode}-{i}"'
                f'{"" if i == 0 else " hidden"}><table><caption>{_e(label)} — games that '
                f'cleared it</caption><thead><tr><th scope="col">Player</th><th scope="col">Season'
                f'</th><th scope="col">L14</th><th scope="col">Post</th></tr></thead>'
                f'<tbody>{"".join(body)}</tbody></table></div>')
    return "".join(out)


def _starter_thresholds(desk: PropDesk) -> str:
    out = []
    for mode, rows in STARTER_THRESHOLDS.items():
        out.append(_pills(mode, [label for label, *_ in rows]))
        for i, (label, *_rest) in enumerate(rows):
            body = "".join(
                f'<tr><th scope="row">{_e(sp.name)}</th><td>{sp.thresholds[mode][i][1].text}</td>'
                f'<td>{sp.thresholds[mode][i][2].text}</td>'
                f'<td class="post">{sp.thresholds[mode][i][3].text}</td></tr>'
                for sp in desk.starters)
            recent = max((len(sp.recent) for sp in desk.starters), default=6)
            out.append(
                f'<div class="pd-th-table" data-m="{mode}" data-t="{mode}-{i}"'
                f'{"" if i == 0 else " hidden"}><table><caption>{_e(label)} — starts that '
                f'cleared it</caption><thead><tr><th scope="col">Starter</th><th scope="col">'
                f'Season</th><th scope="col">Last {recent} recorded</th><th scope="col">Post</th>'
                f'</tr></thead><tbody>{body}</tbody></table></div>')
    return "".join(out)


# --- the section ----------------------------------------------------------------------

def prop_desk_html(desk: PropDesk | None, game_id: str = "") -> str:
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
        f'<section class="pd" data-pd data-pd-game="{_e(game_id)}" data-mode="hits" '
        f'aria-labelledby="pd-title">'
        f'<div class="pd-head"><div><h2 id="pd-title">Playoff Prop Desk</h2>'
        f'<p class="pd-sub">Evidence for player and pitcher decisions</p></div>'
        f'<span class="pd-through">Data through {_e(through)} · regular season ended '
        f'{_e(reg_end)}</span></div>'
        f'<div class="pd-modes" role="group" aria-label="Market" data-pd-modes hidden>{modes}</div>'
        f'{notes}'
        f'<div class="pd-watching" data-pd-watching hidden><span>Watching</span>'
        f'<span data-pd-watch-list></span></div>'
        f'<div class="pd-starters">{starters}</div>'
        f'<div class="pd-lineups">{lineups}</div>'
        f'<div class="pd-thresholds"><div class="pd-th-head"><h3>Thresholds</h3>'
        f'<span class="pd-quiet">Games that cleared each mark. Counts first; a rate only from '
        f'{SMALL} games up. L14 is the last two weeks of the regular season.</span></div>'
        f'{_hitter_thresholds(desk)}{_starter_thresholds(desk)}</div>'
        f'<p class="pd-legend"><span class="pd-sep"></span> regular season ends · '
        f'<span class="pd-v post">2</span> playoff game · strips run oldest → newest · tap a '
        f'hitter for L28, the opponent, the series and the matchup. Built from the play-by-play '
        f'feed, which does not pick up official scoring changes, so a season total can differ '
        f'from MLB’s by a hit. Evidence, not picks: no odds are read and nothing here is scored.</p>'
        f'</section>')
