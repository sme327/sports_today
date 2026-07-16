"""Render functions for the WNBA matchup page (pure HTML; no calculations).

Reuses the shared design-system classes (mlb-* section/identity/matchup/trend
primitives, the icon library, and the opportunity feed) and adds WNBA-specific
pieces (records hero, snapshot cards, W/L form dots, sparklines). Basketball-
designed; values arrive precomputed on the WNBAGamePage model.
"""

from __future__ import annotations

from html import escape

from components.format import logo_img
from components.icons import icon
from components.opportunity_feed import opportunity_feed_html
from domain.wnba_game_page import (
    WNBABattlefield, WNBAHero, WNBAPlayerTrend, WNBAShapePlayer, WNBASnapshot,
    WNBATeamIdentity, WNBATeamTrends,
)


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


def _section(title: str, body: str, ic: str | None = None) -> str:
    icon_html = f'<span class="mlb-h2-ic">{icon(ic)}</span>' if ic else ""
    return (f'<div class="mlb-section"><div class="mlb-section-head">'
            f'<h2>{icon_html}<span>{escape(title)}</span></h2></div>{body}</div>')


def _form_dots(results: tuple[str, ...]) -> str:
    dots = "".join(f'<span class="wnba-dot {"w" if r == "W" else "l"}">{escape(r)}</span>'
                   for r in results)
    return f'<span class="wnba-dots">{dots}</span>' if results else ""


def _headshot_img(url: str | None, alt: str, cls: str) -> str:
    if not url:
        return f'<div class="{cls} op-ph-fallback"></div>'
    return (f'<img class="{cls}" src="{escape(url, quote=True)}" alt="{escape(alt, quote=True)}" '
            f'onerror="this.classList.add(\'op-ph-fallback\');this.removeAttribute(\'src\')">')


# --------------------------------------------------------------- HERO --------
def _hero_featured(feat, label) -> str:
    if not feat:
        return ""
    return (f'<div class="wnba-hero-feat">{_headshot_img(feat.headshot, feat.name, "wnba-hero-face")}'
            f'<div><div class="wnba-hero-feat-name">{escape(feat.name)}</div>'
            f'<div class="wnba-hero-feat-line">{escape(feat.line)}</div></div></div>')


def _hero_score_or_time(h: WNBAHero) -> str:
    if h.state in ("live", "final") and h.away_score is not None and h.home_score is not None:
        badge = ('<span class="game-state final">Final</span>' if h.state == "final"
                 else '<span class="game-state live"><span class="live-dot"></span>LIVE</span>')
        return (f'<div class="wnba-hero-score">{h.away_score}<span class="gs-sep">–</span>'
                f'{h.home_score}</div>{badge}')
    return f'<div class="wnba-hero-time">{escape(h.tip_time)}</div>'


def hero_html(h: WNBAHero) -> str:
    def side(team, logo, record, feat, label, home=False):
        return (f'<div class="wnba-hero-team{" home" if home else ""}">'
                f'{logo_img(logo, team, "wnba-hero-logo")}'
                f'<div class="wnba-hero-side"><div class="wnba-hero-name">{escape(team)}</div>'
                f'<div class="wnba-hero-rec">{escape(record)}</div></div></div>')
    meta = " · ".join(escape(x) for x in ("WNBA", h.venue, h.tip_time) if x)
    series = f'<span class="wnba-hero-series">{escape(h.series)}</span>' if h.series else ""
    return (
        '<div class="wnba-hero">'
        '<div class="wnba-hero-row">'
        f'{side(h.away_team, h.away_logo, h.away_record, h.away_featured, "away")}'
        f'<div class="wnba-hero-mid">{_hero_score_or_time(h)}</div>'
        f'{side(h.home_team, h.home_logo, h.home_record, h.home_featured, "home", home=True)}'
        '</div>'
        f'<div class="wnba-hero-feats">{_hero_featured(h.away_featured, "away")}'
        f'{_hero_featured(h.home_featured, "home")}</div>'
        f'<div class="wnba-hero-meta">{meta}{series}</div>'
        '</div>'
    )


# -------------------------------------------------------- GAME SCRIPT --------
def game_script_html(script: tuple[str, ...]) -> str:
    if not script:
        return ""
    paras = "".join(f"<p>{escape(s)}</p>" for s in script)
    body = f'<div class="mlb-story">{paras}</div>'
    return _section("Game Script", body, "game_shape")


# ----------------------------------------------------------- SNAPSHOT --------
def _snap_cards(cards: tuple[WNBASnapshot, ...]) -> str:
    items = []
    for c in cards:
        sub = f'<span class="wnba-snap-sub">{escape(c.sub)}</span>' if c.sub else ""
        items.append(f'<div class="wnba-snap-card"><span class="wnba-snap-k">{escape(c.label)}</span>'
                     f'<span class="wnba-snap-v">{escape(c.value)}</span>{sub}</div>')
    return f'<div class="wnba-snap-grid">{"".join(items)}</div>'


def snapshot_html(away: tuple, home: tuple, away_team: str, home_team: str) -> str:
    body = (f'<div class="wnba-snap-team"><div class="wnba-snap-name">{escape(away_team)}</div>{_snap_cards(away)}</div>'
            f'<div class="wnba-snap-team"><div class="wnba-snap-name">{escape(home_team)}</div>{_snap_cards(home)}</div>')
    return _section("Game Snapshot", f'<div class="wnba-snap-wrap">{body}</div>', "opportunity")


# ------------------------------------------------------- TEAM IDENTITY -------
def _pct_bar(pct: float | None) -> str:
    if pct is None:
        return '<div class="mlb-bar"><div class="mlb-bar-fill" style="width:0"></div></div>'
    w = max(3, min(100, round(pct)))
    tier = "hi" if pct >= 66 else "lo" if pct <= 33 else "mid"
    return f'<div class="mlb-bar"><div class="mlb-bar-fill {tier}" style="width:{w}%"></div></div>'


def _identity_card(idn: WNBATeamIdentity) -> str:
    labels = "".join(f'<span class="wnba-label">{escape(l)}</span>' for l in idn.labels)
    rows = []
    for m in idn.metrics:
        if m.percentile is None:
            right = '<span class="mlb-metric-na">n/a</span>'
        else:
            t = _tier(m.percentile)
            right = f'<span class="mlb-tier {t[1]}">{t[0]}</span><span class="mlb-pct-sm">{int(round(m.percentile))}</span>'
        rows.append(f'<div class="mlb-metric-row"><span class="mlb-metric-name"><span>{escape(m.name)}</span></span>'
                    f'{_pct_bar(m.percentile)}<span class="mlb-metric-right">{right}</span></div>')
    return (
        f'<div class="mlb-identity-card">'
        f'<div class="mlb-identity-head">{logo_img(idn.logo, idn.team, "mlb-identity-logo")}'
        f'<div><div class="mlb-identity-team">{escape(idn.team)}</div>'
        f'<div class="wnba-identity-meta">{escape(idn.record)} · {_form_dots(idn.form_results)} '
        f'<span class="wnba-streak">{escape(idn.streak)}</span></div></div></div>'
        f'<div class="wnba-labels">{labels}</div>'
        f'<div class="mlb-identity-summary">{escape(idn.summary)}</div>'
        f'<div class="mlb-metrics">{"".join(rows)}</div></div>'
    )


def team_identity_html(away: WNBATeamIdentity, home: WNBATeamIdentity) -> str:
    return _section("Team Identity",
                    f'<div class="mlb-identity-grid">{_identity_card(away)}{_identity_card(home)}</div>',
                    "contact")


# ------------------------------------------------ WHERE THE GAME IS WON ------
def battlefields_html(bfs: tuple[WNBABattlefield, ...]) -> str:
    if not bfs:
        return ""
    items = []
    for b in bfs:
        metrics = "".join(f'<span class="mlb-chip">{escape(x)}</span>' for x in b.supporting_metrics)
        items.append(
            '<div class="mlb-matchup">'
            f'<div class="mlb-matchup-q">{icon("matchup")}<span>{escape(b.title)}</span></div>'
            f'<div class="mlb-matchup-body">{escape(b.explanation)}</div>'
            f'<div class="mlb-chips"><span class="mlb-edge">Edge · {escape(b.advantage)}</span>'
            f'{metrics}<span class="mlb-conf">{escape(b.confidence)} confidence</span></div></div>')
    return _section("Where the Game Will Be Won", f'<div class="mlb-matchups">{"".join(items)}</div>', "matchup")


# ------------------------------------------------ PLAYERS WHO SHAPE ----------
def shape_players_html(players: tuple[WNBAShapePlayer, ...]) -> str:
    if not players:
        return ""
    cards = []
    for p in players:
        cards.append(
            f'<div class="wnba-shape-card">'
            f'<div class="wnba-shape-head">{_headshot_img(p.headshot, p.name, "wnba-shape-face")}'
            f'<div><div class="wnba-shape-name">{escape(p.name)}</div>'
            f'<div class="wnba-shape-team">{escape(p.team)}{" · " + escape(p.position) if p.position else ""}</div></div>'
            f'<span class="wnba-role">{escape(p.role)}</span></div>'
            f'<div class="wnba-shape-line">{escape(p.season_line)}</div>'
            f'<div class="wnba-shape-why">{escape(p.why_tonight)} <span class="wnba-shape-tag">{escape(p.trend)}</span></div>'
            f'</div>')
    return _section("Players Who Shape Tonight", f'<div class="wnba-shape-grid">{"".join(cards)}</div>', "confidence")


# ------------------------------------------------------ TRENDING ------------
def _trend_card(t: WNBAPlayerTrend) -> str:
    cls = "up" if t.direction == "up" else "down"
    return (
        f'<div class="mlb-trend-card {cls}">'
        f'<div class="mlb-trend-head">{_headshot_img(t.headshot, t.name, "mlb-headshot")}'
        f'<div><div class="mlb-trend-name">{escape(t.name)}</div>'
        f'<div class="mlb-trend-team">{escape(t.team)}</div></div>'
        f'<span class="mlb-trend-tag {cls}">{escape(t.category)}</span></div>'
        f'<div class="mlb-trend-expl">{escape(t.explanation)}</div>'
        f'<div class="mlb-trend-windows"><span>{escape(t.recent_summary)}</span>'
        f'<span>{escape(t.baseline_summary)}</span></div></div>')


def trends_html(up: tuple, down: tuple) -> str:
    if not up and not down:
        return _section("Trending Players",
                        '<div class="mlb-empty">Not enough recent games to identify reliable trends.</div>',
                        "recent_form")
    cards = "".join(_trend_card(t) for t in list(up) + list(down))
    return _section("Trending Players", f'<div class="mlb-trend-grid">{cards}</div>', "recent_form")


# ----------------------------------------------------- TEAM TRENDS ----------
def _sparkline(values: tuple[float, ...]) -> str:
    if len(values) < 2:
        return '<span class="wnba-spark-flat"></span>'
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1.0
    w, h, pad = 108, 26, 3
    step = (w - 2 * pad) / (len(values) - 1)
    pts = " ".join(f"{pad + i * step:.1f},{h - pad - (v - lo) / rng * (h - 2 * pad):.1f}"
                   for i, v in enumerate(values))
    last_x = pad + (len(values) - 1) * step
    last_y = h - pad - (values[-1] - lo) / rng * (h - 2 * pad)
    return (f'<svg class="wnba-spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            f'<polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2" fill="currentColor"/></svg>')


def _trend_block(tt: WNBATeamTrends) -> str:
    rows = []
    for s in tt.sparks:
        rows.append(f'<div class="wnba-spark-row"><span class="wnba-spark-k">{escape(s.label)}</span>'
                    f'{_sparkline(s.values)}<span class="wnba-spark-v">{escape(s.display)}</span></div>')
    return (f'<div class="wnba-trend-block"><div class="wnba-trend-team">'
            f'{logo_img(tt.logo, tt.team, "wnba-trend-logo")}<span>{escape(tt.team)}</span></div>'
            f'{"".join(rows)}</div>')


def team_trends_html(away: WNBATeamTrends | None, home: WNBATeamTrends | None) -> str:
    if not away and not home:
        return ""
    blocks = "".join(_trend_block(b) for b in (away, home) if b)
    return _section("Team Trends", f'<div class="wnba-trend-grid">{blocks}</div>', "recent_form")


def opportunities_html(opps) -> str:
    if opps:
        body = opportunity_feed_html(list(opps))
    else:
        body = ('<div class="mlb-empty">No qualifying player opportunities meet the '
                'display threshold for this matchup.</div>')
    return _section("Strongest Player Opportunities", body, "opportunity")


def data_context_html(text: str) -> str:
    return f'<div class="mlb-context">{escape(text)}</div>'
