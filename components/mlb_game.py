"""Render functions for the MLB game page (pure HTML; no calculations).

All values arrive precomputed on the immutable MLBGamePage model. These helpers
only format them into the Sports Today design system with a subtle MLB scorebook
character (deep navy surfaces, compact stat rows).
"""

from __future__ import annotations

from html import escape

from components.format import logo_img
from domain.mlb_game_page import (
    MLBGameHero, MLBGameShape, MLBKeyMatchup, MLBPlayerTrend, MLBStoryline, MLBTeamIdentity,
)


def _pct_bar(percentile: float | None) -> str:
    if percentile is None:
        return '<div class="mlb-bar"><div class="mlb-bar-fill" style="width:0"></div></div>'
    w = max(3, min(100, round(percentile)))
    tier = "hi" if percentile >= 66 else "lo" if percentile <= 33 else "mid"
    return (f'<div class="mlb-bar"><div class="mlb-bar-fill {tier}" '
            f'style="width:{w}%"></div></div>')


def hero_html(h: MLBGameHero) -> str:
    def side(name, logo):
        return (f'<div class="mlb-hero-team">{logo_img(logo, name, "mlb-hero-logo")}'
                f'<span class="mlb-hero-name">{escape(name)}</span></div>')
    if h.probable_pitcher_status == "unavailable":
        pitchers = '<div class="mlb-hero-pitchers">Probable starters not yet available</div>'
    else:
        ap = escape(h.probable_away_pitcher or "TBD")
        hp = escape(h.probable_home_pitcher or "TBD")
        pitchers = (f'<div class="mlb-hero-pitchers"><span class="mlb-pitcher">{ap}</span>'
                    f'<span class="mlb-hero-vs-sm">vs</span>'
                    f'<span class="mlb-pitcher">{hp}</span></div>')
    meta_bits = [b for b in (h.league_context, h.venue, h.scheduled_time) if b]
    meta = " · ".join(escape(b) for b in meta_bits)
    return (
        '<div class="mlb-hero">'
        '<div class="mlb-hero-row">'
        f'{side(h.away_team, h.away_logo_url)}'
        '<div class="mlb-hero-vs">@</div>'
        f'{side(h.home_team, h.home_logo_url)}'
        '</div>'
        f'<div class="mlb-hero-meta">{meta}</div>'
        f'{pitchers}'
        '</div>'
    )


def _section(title: str, body: str, sub: str | None = None) -> str:
    sub_html = f'<span class="mlb-section-sub">{escape(sub)}</span>' if sub else ""
    return (f'<div class="mlb-section"><div class="mlb-section-head">'
            f'<h2>{escape(title)}</h2>{sub_html}</div>{body}</div>')


def game_story_html(story: tuple[str, ...]) -> str:
    if not story:
        return ""
    paras = "".join(f"<p>{escape(s)}</p>" for s in story)
    return _section("What This Game Is About", f'<div class="mlb-story">{paras}</div>')


def _identity_card(idn: MLBTeamIdentity) -> str:
    form_cls = {"up": "up", "down": "down"}.get(
        next((m.trend_direction for m in idn.metrics if m.name == "Recent Form"), None), "steady")
    rows = []
    for m in idn.metrics:
        if m.name == "Recent Form":
            arrow = {"up": "▲", "down": "▼"}.get(m.trend_direction or "", "—")
            right = f'<span class="mlb-form-pill {form_cls}">{arrow} {escape(m.display_value)}</span>'
            rows.append(f'<div class="mlb-metric-row"><span class="mlb-metric-name">{escape(m.name)}</span>'
                        f'{_pct_bar(m.percentile)}{right}</div>')
            continue
        if m.percentile is None:
            right = f'<span class="mlb-metric-na">{escape(m.sample_note or "n/a")}</span>'
        else:
            right = f'<span class="mlb-metric-pct">{int(round(m.percentile))}<span class="mlb-pctl">pctl</span></span>'
        rows.append(f'<div class="mlb-metric-row"><span class="mlb-metric-name">{escape(m.name)}</span>'
                    f'{_pct_bar(m.percentile)}{right}</div>')
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
    body = (f'<div class="mlb-identity-grid">{_identity_card(away)}{_identity_card(home)}</div>')
    return _section("Team Identity", body)


def key_matchups_html(matchups: tuple[MLBKeyMatchup, ...]) -> str:
    if not matchups:
        return ""
    items = []
    for m in matchups:
        metrics = "".join(f'<span class="mlb-chip">{escape(x)}</span>' for x in m.supporting_metrics)
        note = f'<div class="mlb-matchup-note">{escape(m.availability_note)}</div>' if m.availability_note else ""
        items.append(
            '<div class="mlb-matchup">'
            f'<div class="mlb-matchup-top"><div class="mlb-matchup-title">{escape(m.title)}</div>'
            f'<span class="mlb-edge">Edge: {escape(m.advantage)}</span></div>'
            f'<div class="mlb-matchup-body">{escape(m.explanation)}</div>'
            f'<div class="mlb-chips">{metrics}<span class="mlb-conf">{escape(m.confidence)} confidence</span></div>'
            f'{note}</div>')
    return _section("Key Matchups", f'<div class="mlb-matchups">{"".join(items)}</div>')


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
    return _section("Heating Up / Cooling Off", f'<div class="mlb-trend-grid">{cards}</div>')


def game_shape_html(shape: MLBGameShape | None) -> str:
    if shape is None:
        return ""
    facets = [
        ("Shape", shape.label), ("Early edge", shape.early_edge or "—"),
        ("Driver", shape.offensive_driver), ("Volatility", shape.volatility),
        ("Confidence", shape.confidence),
    ]
    tiles = "".join(f'<div class="mlb-shape-tile"><span class="mlb-shape-k">{escape(k)}</span>'
                    f'<span class="mlb-shape-v">{escape(str(v))}</span></div>' for k, v in facets)
    facts = "".join(f"<li>{escape(f)}</li>" for f in shape.supporting_facts)
    body = (f'<div class="mlb-shape-tiles">{tiles}</div>'
            f'<div class="mlb-shape-shape">{escape(shape.likely_shape)}</div>'
            f'<ul class="mlb-shape-facts">{facts}</ul>')
    return _section("Expected Game Shape", body)


def storylines_html(storylines: tuple[MLBStoryline, ...]) -> str:
    if not storylines:
        return ""
    items = []
    for s in storylines:
        facts = " · ".join(escape(f) for f in s.supporting_facts)
        items.append(f'<div class="mlb-storyline"><div class="mlb-storyline-q">{escape(s.title)}</div>'
                     f'<div class="mlb-storyline-a">{escape(s.explanation)}</div>'
                     f'<div class="mlb-storyline-facts">{facts}</div></div>')
    return _section("Storylines to Watch", f'<div class="mlb-storylines">{"".join(items)}</div>')


def data_context_html(text: str) -> str:
    return f'<div class="mlb-context">{escape(text)}</div>'
