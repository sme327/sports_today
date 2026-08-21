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


def _evidence(kind: str, heading: str, body: str = "") -> str:
    """One evidence block. ``body`` may be empty — "No notable risk" says everything
    already, and a second line restating it as "Nothing concerning in recent form"
    was two lines of vertical space for no added information."""
    ic = icon("positive") if kind == "good" else icon("neutral") if kind == "flat" else icon("risk")
    body_html = f'<div class="op-ev-body">{escape(body)}</div>' if body else ""
    return (f'<div class="op-evidence op-{kind}">'
            f'<div class="op-ev-head">{ic}<span>{escape(heading)}</span></div>'
            f'{body_html}</div>')


def _line_html(opp: Opportunity) -> str:
    """The actual recent games, oldest to newest, with cleared games marked.

    A score compresses ten games into one number and hides the shape — three players can
    all score 100 while going 10/10, 9/10 and 9/10 with very different distributions. The
    evidence lines are our judgement; this is the fact underneath, and it is what lets a
    reader disagree with us. Renders nothing when the scorer supplied no line.
    """
    if not opp.recent_line:
        return ""
    cleared = opp.line_cleared
    chips = []
    for i, value in enumerate(opp.recent_line):
        hit = cleared[i] if i < len(cleared) else False
        text = f"{value:g}"
        chips.append(f'<span class="op-lv{" hit" if hit else ""}">{escape(text)}</span>')
    n = len(cleared)
    tally = f"{sum(cleared)}/{n}" if n else ""
    return ('<div class="op-line">'
            f'<span class="op-line-label">Last {len(opp.recent_line)}</span>'
            f'<span class="op-line-vals">{"".join(chips)}</span>'
            f'<span class="op-line-tally">{escape(tally)}</span>'
            '</div>')


def _pick_attrs(opp: Opportunity, game_labels: dict[str, str] | None = None) -> str:
    """``data-pick-*`` attributes carrying everything the shortlist script stores,
    so the client needs no parsing of rendered text. The market key falls back to
    the display label for legacy scorers that never set one — the Results join
    uses the same fallback, so the two sides still agree. The game label lets the
    tray group picks by sport and game; absent (an older caller, an unknown game)
    the tray falls back to the team name."""
    threshold = "" if opp.threshold is None else f"{opp.threshold:g}"
    game_id = str(opp.game_id or "")
    fields = {
        "data-pick-league": opp.league,
        "data-pick-player-id": opp.player_id,
        "data-pick-player": opp.player_name,
        "data-pick-market-key": opp.market_key or opp.market,
        "data-pick-market": opp.market,
        "data-pick-threshold": threshold,
        "data-pick-score": str(opp.opportunity_score),
        "data-pick-team": opp.team_name or "",
        "data-pick-game-id": game_id,
        "data-pick-game": (game_labels or {}).get(game_id, ""),
    }
    return " ".join(f'{k}="{escape(str(v), quote=True)}"' for k, v in fields.items())


def _pick_button(opp: Opportunity) -> str:
    """The affordance is a plain button the static-site script wires up; without JS it
    stays inert and invisible (CSS hides it until the script marks the list ready).
    The label names the player and market: a slate renders eight of these, and eight
    controls reading identically as "Save to shortlist" are indistinguishable in a
    screen reader's element list (the 2026-08-19 accessible-name rule)."""
    label = f"Save to shortlist: {opp.player_name} — {opp.market}"
    return ('<button type="button" class="op-pick" aria-pressed="false" '
            f'aria-label="{escape(label, quote=True)}">{icon("shortlist")}</button>')


def _row_html(opp: Opportunity, game_labels: dict[str, str] | None = None) -> str:
    support_fb, risk_fb = _FALLBACKS.get(opp.league, _DEFAULT_FALLBACK)
    support = opp.primary_support or support_fb
    risk = opp.primary_risk or risk_fb
    if risk in _NEUTRAL_RISKS:
        risk_html = _evidence("flat", "No notable risk")
    else:
        risk_html = _evidence("risk", "Main risk", risk)
    return (
        f'<div class="op-row" {_pick_attrs(opp, game_labels)}>'
        f'{_pick_button(opp)}'
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
        f'{_line_html(opp)}'
        '</div>'
    )


def opportunity_feed_html(opportunities: list[Opportunity],
                          game_labels: dict[str, str] | None = None) -> str:
    """``game_labels`` maps game_id → "Away @ Home" so saved picks can name their
    game in the tray; omitting it degrades to team-name grouping, never an error."""
    rows = "".join(_row_html(o, game_labels) for o in opportunities)
    return f'<div class="op-list">{rows}</div>'
