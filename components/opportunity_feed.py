"""Ranked cross-sport opportunity feed."""

from __future__ import annotations

from html import escape

from components.format import logo_img
from domain.models import Opportunity
from leagues.base import get_adapter

# Preserve the original per-league fallback copy for empty-evidence cases.
_FALLBACKS = {
    "MLB": (
        "Current-season profile supports further review",
        "Opponent and lineup context are incomplete",
    ),
    "WNBA": (
        "Recent role and production support further review",
        "Injury and matchup context are not yet included",
    ),
}
_DEFAULT_FALLBACK = (
    "Recent profile supports further review",
    "Matchup and availability context are not yet included",
)


def _emoji(league: str) -> str:
    adapter = get_adapter(league)
    return adapter.emoji if adapter else ""


def _row_html(opp: Opportunity) -> str:
    support_fb, risk_fb = _FALLBACKS.get(opp.league, _DEFAULT_FALLBACK)
    support = opp.primary_support or support_fb
    risk = opp.primary_risk or risk_fb
    image_html = logo_img(opp.image_url, opp.team_name or "", "op-team-logo")
    return (
        f'<div class="op-row">'
        f'<div class="op-score">{opp.opportunity_score}</div>'
        f'<div class="op-identity">'
        f'<span class="op-sport">{_emoji(opp.league)}</span>'
        f'{image_html}<div>'
        f'<div class="op-player">{escape(opp.player_name)}</div>'
        f'<div class="op-market">{escape(opp.market)}</div>'
        f'<div class="op-team">{escape(opp.team_name or "")}</div>'
        f'</div></div>'
        f'<div class="evidence-good"><div class="evidence-title">Why it stands out</div>'
        f'<div class="evidence-body">{escape(support)}</div></div>'
        f'<div class="evidence-risk"><div class="evidence-title">What could go wrong</div>'
        f'<div class="evidence-body">{escape(risk)}</div></div>'
        f'</div>'
    )


def opportunity_feed_html(opportunities: list[Opportunity]) -> str:
    rows = "".join(_row_html(o) for o in opportunities)
    return f'<div class="op-list">{rows}</div>'
