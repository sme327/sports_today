"""Ranked cross-sport opportunity feed.

Each row is player-first: score, a merged avatar (player headshot with a small
team-logo badge), player/opportunity/team text, then green "why it stands out"
and red "what could go wrong" evidence. League-agnostic; the sport is implied by
the market, so no separate sport-ball icon is shown. Images fail gracefully.
"""

from __future__ import annotations

from html import escape

from components.icons import icon
from domain.models import Opportunity

# Fallback evidence copy for empty-evidence cases. The risk side is performance-
# framed, never a data-completeness caveat (those live in a section-level note, so a
# high score is never paired with an "we didn't model X" apology).
_FALLBACKS = {
    "MLB": ("Recent form supports the pick", "No standout red flags in recent form"),
    "WNBA": ("Recent role and production support the pick",
             "No standout red flags in recent form"),
}
_DEFAULT_FALLBACK = ("Recent profile supports the pick",
                     "No standout red flags in recent form")

# Risk copy that means "nothing concerning" — rendered visually neutral (calm gray),
# not in the coral risk treatment, so a clean pick doesn't read as a warning.
_NEUTRAL_RISKS = {"No standout red flags in recent form"}

# Broken/lost images fall to a neutral silhouette, never a broken-image glyph.
_ON_ERR = "this.classList.add('op-ph-fallback');this.removeAttribute('src')"


def _zoom_class(league: str) -> str:
    # League-specific headshot crop/zoom (WNBA sources sit smaller in frame).
    return {"MLB": "op-zoom-mlb", "WNBA": "op-zoom-wnba"}.get(league, "op-zoom-gen")


def _avatar(headshot: str | None, team_logo: str | None, alt: str, league: str) -> str:
    """Merged avatar: circular headshot + overlapping team-logo badge.

    The photo lives in an overflow-hidden circular wrapper so it can be scaled
    (to fill the circle) without growing the circle or clipping the badge.
    Fallback order: headshot + badge -> headshot only -> team logo only ->
    neutral silhouette. No broken-image icons.
    """
    a = escape(alt, quote=True)
    badge = ""
    if team_logo:
        badge = (f'<img class="op-badge" src="{escape(team_logo, quote=True)}" alt="" '
                 f'onerror="this.style.display=\'none\'">')
    if headshot:
        photo = (f'<img class="op-photo {_zoom_class(league)}" src="{escape(headshot, quote=True)}" '
                 f'alt="{a}" onerror="{_ON_ERR}">')
        return f'<div class="op-avatar"><div class="op-photo-wrap">{photo}</div>{badge}</div>'
    if team_logo:  # no headshot: team logo becomes the avatar, no badge
        photo = (f'<img class="op-photo logo" src="{escape(team_logo, quote=True)}" '
                 f'alt="{a}" onerror="{_ON_ERR}">')
        return f'<div class="op-avatar"><div class="op-photo-wrap">{photo}</div></div>'
    return ('<div class="op-avatar"><div class="op-photo-wrap">'
            '<div class="op-photo op-ph-fallback"></div></div></div>')


def _evidence(kind: str, heading: str, body: str) -> str:
    ic = icon("positive") if kind == "good" else icon("neutral") if kind == "flat" else icon("risk")
    return (f'<div class="op-evidence op-{kind}">'
            f'<div class="op-ev-head">{ic}<span>{escape(heading)}</span></div>'
            f'<div class="op-ev-body">{escape(body)}</div></div>')


def _row_html(opp: Opportunity) -> str:
    support_fb, risk_fb = _FALLBACKS.get(opp.league, _DEFAULT_FALLBACK)
    support = opp.primary_support or support_fb
    risk = opp.primary_risk or risk_fb
    if risk in _NEUTRAL_RISKS:
        risk_html = _evidence("flat", "No notable risk", "Nothing concerning in recent form")
    else:
        risk_html = _evidence("risk", "Main risk", risk)
    return (
        '<div class="op-row">'
        f'<div class="op-score">{opp.opportunity_score}</div>'
        '<div class="op-identity">'
        f'{_avatar(opp.headshot_url, opp.image_url, opp.player_name, opp.league)}'
        '<div class="op-info">'
        f'<div class="op-player">{escape(opp.player_name)}</div>'
        f'<div class="op-market">{escape(opp.market)}</div>'
        f'<div class="op-team">{escape(opp.team_name or "")}</div>'
        '</div></div>'
        f'{_evidence("good", "Why it stands out", support)}'
        f'{risk_html}'
        '</div>'
    )


def opportunity_feed_html(opportunities: list[Opportunity]) -> str:
    rows = "".join(_row_html(o) for o in opportunities)
    return f'<div class="op-list">{rows}</div>'
