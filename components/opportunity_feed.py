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

# Fallback evidence copy for empty-evidence cases.
_FALLBACKS = {
    "MLB": ("Current-season profile supports further review",
            "Opponent and lineup context are incomplete"),
    "WNBA": ("Recent role and production support further review",
             "Injury and matchup context are not yet included"),
}
_DEFAULT_FALLBACK = ("Recent profile supports further review",
                     "Matchup and availability context are not yet included")

# Broken/lost images fall to a neutral silhouette, never a broken-image glyph.
_ON_ERR = "this.classList.add('op-ph-fallback');this.removeAttribute('src')"


def _avatar(headshot: str | None, team_logo: str | None, alt: str) -> str:
    """Merged avatar: circular headshot + overlapping team-logo badge.

    Fallback order: headshot + badge -> headshot only -> team logo only ->
    neutral silhouette. No broken-image icons.
    """
    a = escape(alt, quote=True)
    badge = ""
    if team_logo:
        badge = (f'<img class="op-badge" src="{escape(team_logo, quote=True)}" alt="" '
                 f'onerror="this.style.display=\'none\'">')
    if headshot:
        photo = (f'<img class="op-photo" src="{escape(headshot, quote=True)}" '
                 f'alt="{a}" onerror="{_ON_ERR}">')
        return f'<div class="op-avatar">{photo}{badge}</div>'
    if team_logo:  # no headshot: team logo becomes the avatar, no badge
        photo = (f'<img class="op-photo logo" src="{escape(team_logo, quote=True)}" '
                 f'alt="{a}" onerror="{_ON_ERR}">')
        return f'<div class="op-avatar">{photo}</div>'
    return '<div class="op-avatar"><div class="op-photo op-ph-fallback"></div></div>'


def _evidence(kind: str, heading: str, body: str) -> str:
    ic = icon("positive") if kind == "good" else icon("risk")
    return (f'<div class="op-evidence op-{kind}">'
            f'<div class="op-ev-head">{ic}<span>{escape(heading)}</span></div>'
            f'<div class="op-ev-body">{escape(body)}</div></div>')


def _row_html(opp: Opportunity) -> str:
    support_fb, risk_fb = _FALLBACKS.get(opp.league, _DEFAULT_FALLBACK)
    support = opp.primary_support or support_fb
    risk = opp.primary_risk or risk_fb
    return (
        '<div class="op-row">'
        f'<div class="op-score">{opp.opportunity_score}</div>'
        '<div class="op-identity">'
        f'{_avatar(opp.headshot_url, opp.image_url, opp.player_name)}'
        '<div class="op-info">'
        f'<div class="op-player">{escape(opp.player_name)}</div>'
        f'<div class="op-market">{escape(opp.market)}</div>'
        f'<div class="op-team">{escape(opp.team_name or "")}</div>'
        '</div></div>'
        f'{_evidence("good", "Why it stands out", support)}'
        f'{_evidence("risk", "What could go wrong", risk)}'
        '</div>'
    )


def opportunity_feed_html(opportunities: list[Opportunity]) -> str:
    rows = "".join(_row_html(o) for o in opportunities)
    return f'<div class="op-list">{rows}</div>'
