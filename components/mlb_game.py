"""Render functions for the MLB game page (pure HTML; no calculations).

V1.2 polish: plain-English hero, role-tagged insight cards, a narrative game
shape, de-numbered storylines, and a small set of restrained monochrome SVG icons
(no emoji) that aid scanning. All values arrive precomputed on the page model.
"""

from __future__ import annotations

from html import escape

from components.format import logo_img
from components.icons import icon as _icon
from domain.mlb_game_page import (
    MLBGameHero, MLBGameShape, MLBKeyMatchup, MLBPlayerTrend, MLBStoryline, MLBTeamIdentity,
)

_DIM_ICON = {"Power": "power", "Contact": "contact", "Plate Discipline": "discipline",
             "Speed": "speed", "RISP": "risp"}
_INSIGHT_ROLES = [("Biggest Advantage", "advantage"), ("Swing Factor", "swing"),
                  ("Momentum", "momentum")]


def _ordinal(n) -> str:
    if n is None:
        return "—"
    n = int(round(n))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _tier(pct: float | None) -> tuple[str, str] | None:
    if pct is None:
        return None
    if pct >= 85:
        return "Elite", "hi"
    if pct >= 66:
        return "Above Avg", "hi"
    if pct >= 45:
        return "Average", "mid"
    if pct >= 25:
        return "Below Avg", "lo"
    return "Well Below", "lo"


def _hand_label(hand: str | None) -> str:
    return {"L": "LHP", "R": "RHP"}.get(hand or "", "")


# --------------------------------------------------------------- HERO --------
def _hero_side(name, logo, form_note, form_dir, pitcher, hand, pitcher_note, home=False) -> str:
    form = ""
    if form_note:
        cls = form_dir if form_dir in ("up", "down") else "steady"
        form = (f'<span class="mlb-form-pill {cls}">{_icon("form-" + cls)}'
                f'<span>{escape(form_note)}</span></span>')
    if pitcher:
        lead = " ".join(b for b in (_hand_label(hand), escape(pitcher)) if b)
        tail = f' · {escape(pitcher_note)}' if pitcher_note else ""
        sp = f'<div class="mlb-hero-sp">{lead}{tail}</div>'
    else:
        sp = '<div class="mlb-hero-sp tbd">Starter TBD</div>'
    return (
        f'<div class="mlb-hero-team{" home" if home else ""}">'
        f'{logo_img(logo, name, "mlb-hero-logo")}'
        f'<div class="mlb-hero-side">'
        f'<span class="mlb-hero-name">{escape(name)}</span>{form}{sp}'
        f'</div></div>'
    )


def hero_html(h: MLBGameHero) -> str:
    meta_bits = [b for b in (h.league_context, h.venue, h.scheduled_time) if b]
    meta = " · ".join(escape(b) for b in meta_bits)
    note = ""
    if h.probable_pitcher_status == "unavailable":
        note = '<div class="mlb-hero-note">Probable starters not yet available</div>'
    return (
        '<div class="mlb-hero">'
        '<div class="mlb-hero-row">'
        f'{_hero_side(h.away_team, h.away_logo_url, h.away_form_note, h.away_form_dir, h.probable_away_pitcher, h.away_pitcher_hand, h.away_pitcher_note)}'
        '<div class="mlb-hero-vs">@</div>'
        f'{_hero_side(h.home_team, h.home_logo_url, h.home_form_note, h.home_form_dir, h.probable_home_pitcher, h.home_pitcher_hand, h.home_pitcher_note, home=True)}'
        '</div>'
        f'<div class="mlb-hero-meta">{meta}</div>'
        f'{note}'
        '</div>'
    )


def _section(title: str, body: str, icon: str | None = None) -> str:
    ic = f'<span class="mlb-h2-ic">{_icon(icon)}</span>' if icon else ""
    return (f'<div class="mlb-section"><div class="mlb-section-head">'
            f'<h2>{ic}<span>{escape(title)}</span></h2></div>{body}</div>')


# ------------------------------------------------- WHAT THIS GAME IS ABOUT ---
def game_story_html(story: tuple[str, ...]) -> str:
    if not story:
        return ""
    cards = []
    for i, s in enumerate(story):
        role, icon = _INSIGHT_ROLES[i] if i < len(_INSIGHT_ROLES) else ("Key Point", "baseball")
        cards.append(
            f'<div class="mlb-insight"><div class="mlb-insight-role">{_icon(icon)}'
            f'<span>{escape(role)}</span></div><p>{escape(s)}</p></div>')
    return _section("What This Game Is About", f'<div class="mlb-insights">{"".join(cards)}</div>')


# ------------------------------------------------------------ IDENTITY -------
def _pct_bar(percentile: float | None) -> str:
    if percentile is None:
        return '<div class="mlb-bar"><div class="mlb-bar-fill" style="width:0"></div></div>'
    w = max(3, min(100, round(percentile)))
    tier = "hi" if percentile >= 66 else "lo" if percentile <= 33 else "mid"
    return f'<div class="mlb-bar"><div class="mlb-bar-fill {tier}" style="width:{w}%"></div></div>'


def _identity_card(idn: MLBTeamIdentity) -> str:
    rows = []
    for m in idn.metrics:
        if m.name == "Recent Form":
            cls = m.trend_direction if m.trend_direction in ("up", "down") else "steady"
            icon = _icon("form-" + cls)
            right = f'<span class="mlb-form-pill {cls}">{icon}<span>{escape(m.display_value)}</span></span>'
        else:
            icon = _icon(_DIM_ICON.get(m.name, ""))
            if m.percentile is None:
                right = f'<span class="mlb-metric-na">{escape(m.sample_note or "n/a")}</span>'
            else:
                tier = _tier(m.percentile)
                right = (f'<span class="mlb-tier {tier[1]}">{tier[0]}</span>'
                         f'<span class="mlb-pct-sm">{int(round(m.percentile))}</span>')
        name_cell = f'<span class="mlb-metric-name">{icon}<span>{escape(m.name)}</span></span>'
        rows.append(f'<div class="mlb-metric-row">{name_cell}{_pct_bar(m.percentile)}'
                    f'<span class="mlb-metric-right">{right}</span></div>')
    return (
        f'<div class="mlb-identity-card">'
        f'<div class="mlb-identity-head">{logo_img(idn.logo_url, idn.team, "mlb-identity-logo")}'
        f'<div><div class="mlb-identity-team">{escape(idn.team)}</div>'
        f'<div class="mlb-identity-sample">{escape(idn.sample_context)}</div></div></div>'
        f'<div class="mlb-identity-summary">{escape(idn.identity_summary)}</div>'
        f'<div class="mlb-metrics">{"".join(rows)}</div>'
        f'<div class="mlb-form-evidence">{escape(idn.recent_form_evidence)}</div>'
        f'</div>'
    )


def team_identity_html(away: MLBTeamIdentity, home: MLBTeamIdentity) -> str:
    return _section("Team Identity",
                    f'<div class="mlb-identity-grid">{_identity_card(away)}{_identity_card(home)}</div>')


# ------------------------------------------------------------ MATCHUPS -------
def key_matchups_html(matchups: tuple[MLBKeyMatchup, ...]) -> str:
    if not matchups:
        return ""
    items = []
    for m in matchups:
        metrics = "".join(f'<span class="mlb-chip">{escape(x)}</span>' for x in m.supporting_metrics)
        note = f'<div class="mlb-matchup-note">{escape(m.availability_note)}</div>' if m.availability_note else ""
        items.append(
            '<div class="mlb-matchup">'
            f'<div class="mlb-matchup-q">{_icon("matchup")}<span>{escape(m.title)}</span></div>'
            f'<div class="mlb-matchup-body">{escape(m.explanation)}</div>'
            f'<div class="mlb-chips"><span class="mlb-edge">Edge · {escape(m.advantage)}</span>'
            f'{metrics}<span class="mlb-conf">{escape(m.confidence)} confidence</span></div>'
            f'{note}</div>')
    return _section("Key Matchups", f'<div class="mlb-matchups">{"".join(items)}</div>', "matchup")


# ------------------------------------------------- HEATING UP / COOLING OFF --
def _trend_card(t: MLBPlayerTrend) -> str:
    cls = "up" if t.direction == "up" else "down"
    tag = "Heating Up" if t.direction == "up" else "Cooling Off"
    head = (f'<img class="mlb-headshot" src="{escape(t.headshot_url or "", quote=True)}" '
            f'alt="{escape(t.player_name, quote=True)}" '
            f'onerror="this.classList.add(\'img-fallback\');this.removeAttribute(\'src\')">')
    return (
        f'<div class="mlb-trend-card {cls}">'
        f'<div class="mlb-trend-head">{head}'
        f'<div><div class="mlb-trend-name">{escape(t.player_name)}</div>'
        f'<div class="mlb-trend-team">{escape(t.team)}</div></div>'
        f'<span class="mlb-trend-tag {cls}">{tag}</span></div>'
        f'<div class="mlb-trend-expl">{escape(t.explanation)}</div>'
        f'<div class="mlb-trend-windows"><span>{escape(t.recent_window)}: {escape(t.recent_summary)}</span>'
        f'<span>{escape(t.baseline_window)}: {escape(t.baseline_summary)}</span></div>'
        f'</div>')


def player_trends_html(heating: tuple[MLBPlayerTrend, ...], cooling: tuple[MLBPlayerTrend, ...]) -> str:
    if not heating and not cooling:
        return _section("Heating Up / Cooling Off",
                        '<div class="mlb-empty">Not enough recent plate appearances to identify a reliable trend.</div>')
    cards = "".join(_trend_card(t) for t in list(heating) + list(cooling))
    return _section("Heating Up / Cooling Off", f'<div class="mlb-trend-grid">{cards}</div>', "recent_form")


# --------------------------------------------------------- GAME SHAPE --------
def game_shape_html(shape: MLBGameShape | None) -> str:
    if shape is None:
        return ""
    prose = " ".join(shape.narrative[1:]) if len(shape.narrative) > 1 else shape.likely_shape
    facets = []
    if shape.early_edge:
        facets.append(("Early edge", shape.early_edge))
    facets += [("Driver", shape.offensive_driver), ("Volatility", shape.volatility)]
    facet_html = " ".join(
        f'<span class="mlb-shape-facet"><span class="k">{escape(k)}</span> '
        f'<span class="v">{escape(str(v))}</span></span>' for k, v in facets)
    facts = "".join(f"<li>{escape(f)}</li>" for f in shape.supporting_facts)
    body = (
        '<div class="mlb-shape">'
        '<div class="mlb-shape-headline">'
        f'<span class="mlb-shape-label">{escape(shape.label)}</span>'
        f'<span class="mlb-shape-conf">{escape(shape.confidence)} confidence</span></div>'
        f'<p class="mlb-shape-lead">{escape(prose)}</p>'
        f'<div class="mlb-shape-facets">{facet_html}</div>'
        f'<ul class="mlb-shape-facts">{facts}</ul>'
        '</div>')
    return _section("Expected Game Shape", body, "game_shape")


# --------------------------------------------------------- STORYLINES --------
def storylines_html(storylines: tuple[MLBStoryline, ...]) -> str:
    if not storylines:
        return ""
    items = []
    for s in storylines:
        facts = " · ".join(escape(f) for f in s.supporting_facts)
        facts_html = f'<div class="mlb-storyline-facts">{facts}</div>' if facts else ""
        items.append(
            '<div class="mlb-storyline">'
            f'<span class="mlb-storyline-ic">{_icon("baseball")}</span>'
            '<div class="mlb-storyline-body">'
            f'<div class="mlb-storyline-q">{escape(s.title)}</div>'
            f'<div class="mlb-storyline-a">{escape(s.explanation)}</div>'
            f'{facts_html}</div></div>')
    return _section("Storylines to Watch", f'<div class="mlb-storylines">{"".join(items)}</div>', "storyline")


def data_context_html(text: str) -> str:
    return f'<div class="mlb-context">{escape(text)}</div>'
