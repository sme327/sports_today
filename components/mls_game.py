"""Render functions for the MLS matchup page (pure HTML; no calculations).

Soccer-designed. Reuses the shared design-system section shell and the icon
library, and adds soccer-specific pieces: W/D/L form dots, a three-way tactical
lean bar, a CSS/SVG formation pitch, an attacking profile, and the "What to
watch" timeline. Every section shows a data-state badge so honest, unavailable
sections read as deliberate — never broken. Values arrive precomputed on the
MLSGamePage model.
"""

from __future__ import annotations

from html import escape

from components.format import logo_img
from components.icons import icon
from domain.mls_game_page import (
    DataState, MLSAttacking, MLSDiscipline, MLSHero, MLSLineup, MLSLineups,
    MLSPlayersToWatch, MLSSnapshot, MLSStorylines, MLSTactical, MLSTimeline,
    MLSHonestGaps,
)


# ------------------------------------------------------------- PRIMITIVES ----
def _badge(state: DataState) -> str:
    return f'<span class="mls-badge {state.tone}">{escape(state.badge)}</span>'


def _section(title: str, body: str, ic: str | None = None,
             state: DataState | None = None) -> str:
    icon_html = f'<span class="mlb-h2-ic">{icon(ic)}</span>' if ic else ""
    badge = _badge(state) if state is not None else ""
    return (f'<div class="mlb-section"><div class="mlb-section-head mls-head">'
            f'<h2>{icon_html}<span>{escape(title)}</span></h2>{badge}</div>{body}</div>')


def _safe_accent(color: str | None) -> str:
    """A team color guaranteed to read on the charcoal canvas.

    Very dark brand colors (e.g. a black primary) are lightened toward white so
    the accent never disappears; missing colors fall back to the brand orange.
    """
    if not color or not color.startswith("#") or len(color) != 7:
        return "var(--brand)"
    try:
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    except ValueError:
        return "var(--brand)"
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    if lum < 0.24:  # too dark for the canvas — blend toward white
        r = round(r + (255 - r) * 0.55)
        g = round(g + (255 - g) * 0.55)
        b = round(b + (255 - b) * 0.55)
    return f"#{r:02x}{g:02x}{b:02x}"


def _form_dots(form: tuple[str, ...]) -> str:
    if not form:
        return '<span class="mls-form-na">No recent form</span>'
    cls = {"W": "w", "D": "d", "L": "l"}
    dots = "".join(f'<span class="mls-dot {cls.get(r, "d")}" title="{escape(r)}">{escape(r)}</span>'
                   for r in form)
    return f'<span class="mls-dots">{dots}</span>'


# --------------------------------------------------------------- HERO --------
def _hero_center(h: MLSHero) -> str:
    if h.state in ("live", "final") and h.away_score is not None and h.home_score is not None:
        badge = ('<span class="game-state final">Final</span>' if h.state == "final"
                 else '<span class="game-state live"><span class="live-dot"></span>LIVE</span>')
        detail = f'<div class="mls-hero-detail">{escape(h.status_detail)}</div>' if h.status_detail else ""
        return (f'<div class="mls-hero-score">{h.away_score}<span class="gs-sep">–</span>'
                f'{h.home_score}</div>{badge}{detail}')
    return (f'<div class="mls-hero-kick">{escape(h.kickoff)}</div>'
            f'<div class="mls-hero-vs">Kickoff</div>')


def _hero_side(team, home: bool) -> str:
    accent = _safe_accent(team.color)
    pts = f'<span class="mls-hero-pts">{escape(team.points_display)}</span>' if team.points_display else ""
    rec = f'{escape(team.record)} · ' if team.record else ""
    standing = (f'<div class="mls-hero-standing">{escape(team.standing)}</div>'
                if team.standing else "")
    return (
        f'<div class="mls-hero-team{" home" if home else ""}">'
        f'{logo_img(team.logo, team.name, "mls-hero-logo")}'
        f'<div class="mls-hero-side">'
        f'<div class="mls-hero-name">{escape(team.short)}</div>'
        f'<div class="mls-hero-rec">{rec}{pts}</div>'
        f'{_form_dots(team.form)}'
        f'{standing}'
        f'<span class="mls-hero-accent" style="background:{accent}"></span>'
        f'</div></div>'
    )


def hero_html(h: MLSHero) -> str:
    meta = " · ".join(escape(x) for x in (h.competition, h.venue, h.broadcast) if x)
    return (
        '<div class="mls-hero">'
        '<div class="mls-hero-row">'
        f'{_hero_side(h.away, home=False)}'
        f'<div class="mls-hero-mid">{_hero_center(h)}</div>'
        f'{_hero_side(h.home, home=True)}'
        '</div>'
        f'<div class="mls-hero-meta">{meta}</div>'
        '</div>'
    )


# --------------------------------------------------- COMPARISON ROWS ---------
def _cmp_row(label: str, away: str, home: str, better: str | None,
             state: DataState) -> str:
    if state is DataState.UNAVAILABLE:
        a_cls = h_cls = "mls-cmp-v na"
        tag = '<span class="mls-cmp-soon">soon</span>'
        away = home = "—"
    else:
        a_cls = "mls-cmp-v" + (" best" if better == "away" else "")
        h_cls = "mls-cmp-v" + (" best" if better == "home" else "")
        tag = ""
    return (f'<div class="mls-cmp-row">'
            f'<span class="{a_cls}">{escape(away)}</span>'
            f'<span class="mls-cmp-k">{escape(label)}{tag}</span>'
            f'<span class="{h_cls}">{escape(home)}</span></div>')


# --------------------------------------------------- MATCHUP SNAPSHOT --------
def snapshot_html(s: MLSSnapshot, away_team: str, home_team: str) -> str:
    head = (f'<div class="mls-cmp-head"><span>{escape(away_team)}</span>'
            f'<span></span><span>{escape(home_team)}</span></div>')
    rows = "".join(_cmp_row(r.label, r.away_value, r.home_value, r.better, r.state)
                   for r in s.rows)
    note = f'<div class="mls-note">{escape(s.note)}</div>'
    return _section("Matchup Snapshot", f'<div class="mls-cmp">{head}{rows}</div>{note}',
                    "opportunity", s.state)


# --------------------------------------------------- TACTICAL MATCHUP --------
def _lean_bar(lean: str | None) -> str:
    # Three zones (away | even | home). Marker centered when awaiting data.
    pos = {"away": 16, "even": 50, "home": 84}.get(lean or "", 50)
    idle = " idle" if lean is None else ""
    return (f'<div class="mls-lean{idle}">'
            f'<span class="mls-lean-track"></span>'
            f'<span class="mls-lean-dot" style="left:{pos}%"></span></div>')


def _edge_chip(lean: str | None, confidence: str) -> str:
    label = {"home": "Home edge", "away": "Away edge", "even": "Even"}.get(lean or "", "—")
    conf = f'<span class="mls-tac-conf">{escape(confidence)}</span>' if confidence else ""
    tone = "even" if lean == "even" else "lean"
    return f'<span class="mls-tac-edge {tone}">{escape(label)}</span>{conf}'


def _similar_block(message: str) -> str:
    return (f'<div class="mls-similar">{icon("tactics")}'
            f'<span>{escape(message)}</span></div>')


def tactical_html(t: MLSTactical) -> str:
    note = f'<div class="mls-note">{escape(t.note)}</div>'
    if not t.rows and t.summary:
        body = _similar_block(t.summary)
        return _section("Tactical Matchup", f'{body}{note}', "tactics", t.state)
    rows = []
    for r in t.rows:
        if r.state is DataState.UNAVAILABLE:
            top_right = '<span class="mls-tac-await">Awaiting team style data</span>'
            bar_row = _lean_bar(r.lean)
        else:
            top_right = _edge_chip(r.lean, r.confidence)
            bar_row = (f'<div class="mls-tac-bar-row">'
                       f'<span class="mls-tac-val">{escape(r.away_label)}</span>'
                       f'{_lean_bar(r.lean)}'
                       f'<span class="mls-tac-val">{escape(r.home_label)}</span></div>')
        rows.append(
            f'<div class="mls-tac-row">'
            f'<div class="mls-tac-top"><span class="mls-tac-dim">{escape(r.dimension)}</span>'
            f'{top_right}</div>'
            f'{bar_row}'
            f'<div class="mls-tac-expl">{escape(r.explanation)}</div></div>')
    return _section("Tactical Matchup", f'<div class="mls-tac">{"".join(rows)}</div>{note}',
                    "tactics", t.state)


# --------------------------------------------------- KEY STORYLINES ----------
def storylines_html(s: MLSStorylines) -> str:
    if s.state is DataState.UNAVAILABLE or not s.items:
        body = f'<div class="mlb-empty">{escape(s.note)}</div>'
        return _section("Key Storylines", body, "storyline", s.state)
    items = []
    for st in s.items:
        ic = {"up": "form-up", "down": "form-down"}.get(st.tone, "storyline")
        facts = " · ".join(escape(f) for f in st.evidence)
        items.append(
            '<div class="mlb-storyline">'
            f'<span class="mlb-storyline-ic mls-tone-{escape(st.tone)}">{icon(ic)}</span>'
            '<div class="mlb-storyline-body">'
            f'<div class="mlb-storyline-q">{escape(st.title)}</div>'
            f'<div class="mlb-storyline-a">{escape(st.detail)}</div>'
            f'<div class="mlb-storyline-facts">{facts} · {escape(st.confidence)} confidence</div>'
            '</div></div>')
    note = f'<div class="mls-note">{escape(s.note)}</div>'
    return _section("Key Storylines", f'<div class="mlb-storylines">{"".join(items)}</div>{note}',
                    "storyline", s.state)


# --------------------------------------------------- PROJECTED LINEUPS -------
def _pitch(lu: MLSLineup) -> str:
    accent = _safe_accent(lu.color)
    tokens = []
    for sl in lu.slots:
        label = escape(sl.name) if sl.name else escape(sl.role)
        empty = "" if sl.name else " empty"
        tokens.append(
            f'<div class="mls-slot{empty}" style="left:{sl.x}%;bottom:{sl.y}%;'
            f'--slot-accent:{accent}"><span>{label}</span></div>')
    form_label = escape(lu.formation) if lu.formation else "Formation TBD"
    return (
        f'<div class="mls-pitch-wrap">'
        f'<div class="mls-pitch-head"><span class="mls-pitch-team">{escape(lu.team)}</span>'
        f'<span class="mls-pitch-form">{form_label}</span></div>'
        f'<div class="mls-pitch">'
        f'<div class="mls-pitch-lines"></div>'
        f'{"".join(tokens)}</div>'
        f'<div class="mls-pitch-note">{escape(lu.note)}</div></div>')


def lineups_html(lu: MLSLineups) -> str:
    body = f'<div class="mls-pitch-grid">{_pitch(lu.away)}{_pitch(lu.home)}</div>'
    return _section("Projected Lineups", body, "pitch", lu.state)


# --------------------------------------------------- PLAYERS TO WATCH --------
def players_html(p: MLSPlayersToWatch) -> str:
    cards = []
    for a in p.archetypes:
        who = escape(a.player) if a.player else "Awaiting squad data"
        who_cls = "mls-arch-who" if a.player else "mls-arch-who empty"
        cards.append(
            f'<div class="mls-arch-card">'
            f'<div class="mls-arch-role">{escape(a.name)}</div>'
            f'<div class="{who_cls}">{who}</div>'
            f'<div class="mls-arch-desc">{escape(a.description)}</div></div>')
    note = f'<div class="mls-note">{escape(p.note)}</div>'
    return _section("Players to Watch", f'<div class="mls-arch-grid">{"".join(cards)}</div>{note}',
                    "confidence", p.state)


# --------------------------------------------------- ATTACKING PROFILE -------
def attacking_html(a: MLSAttacking) -> str:
    note = f'<div class="mls-note">{escape(a.note)}</div>'
    if not a.dimensions and a.summary:
        return _section("Attacking Profile", f'{_similar_block(a.summary)}{note}', "attack", a.state)
    head = (f'<div class="mls-cmp-head"><span>{escape(a.away_team)}</span>'
            f'<span></span><span>{escape(a.home_team)}</span></div>')
    rows = "".join(_cmp_row(d.label, d.away_value, d.home_value, d.better, d.state)
                   for d in a.dimensions)
    return _section("Attacking Profile", f'<div class="mls-cmp">{head}{rows}</div>{note}',
                    "attack", a.state)


# --------------------------------------------------- DISCIPLINE --------------
def discipline_html(d: MLSDiscipline) -> str:
    note = f'<div class="mls-note">{escape(d.note)}</div>'
    if not d.rows and d.summary:
        return _section("Discipline", f'{_similar_block(d.summary)}{note}', "discipline", d.state)
    rows = "".join(_cmp_row(r.label, r.away_value, r.home_value, r.better, r.state)
                   for r in d.rows)
    return _section("Discipline", f'<div class="mls-cmp mls-cmp-tight">{rows}</div>{note}',
                    "discipline", d.state)


# --------------------------------------------------- WHAT TO WATCH TIMELINE --
def timeline_html(t: MLSTimeline) -> str:
    items = []
    for ph in t.phases:
        items.append(
            f'<div class="mls-tl-item">'
            f'<div class="mls-tl-marker">{escape(ph.marker)}</div>'
            f'<div class="mls-tl-body"><div class="mls-tl-title">{escape(ph.title)}</div>'
            f'<div class="mls-tl-guide">{escape(ph.guidance)}</div></div></div>')
    note = f'<div class="mls-note">{escape(t.note)}</div>'
    return _section("What to Watch", f'<div class="mls-tl">{"".join(items)}</div>{note}',
                    "timeline", t.state)


# --------------------------------------------------- HONEST GAPS -------------
def honest_gaps_html(g: MLSHonestGaps) -> str:
    if not g.items:
        return ""
    items = []
    for gap in g.items:
        items.append(
            f'<div class="mls-gap"><span class="mls-gap-ic">{icon("risk")}</span>'
            f'<div><div class="mls-gap-label">{escape(gap.label)}</div>'
            f'<div class="mls-gap-detail">{escape(gap.detail)}</div></div></div>')
    return _section("Honest Gaps", f'<div class="mls-gaps">{"".join(items)}</div>', "risk")


def data_context_html(text: str) -> str:
    return f'<div class="mlb-context">{escape(text)}</div>'
