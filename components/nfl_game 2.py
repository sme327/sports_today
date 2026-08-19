"""NFL matchup-page renderers (pure HTML strings). Calm, evidence-first, comparison-led:
the analysis (identity + battlefields) as a leakage-safe preview, with the final result
shown as what happened. Orange is reserved for the winner + the favored side."""

from __future__ import annotations

from html import escape

from services.nfl_game_page import (
    NFLFormLine, NFLGamePage, NFLHero, NFLIdentityRow, NFLSpotlight,
)


def _team_col(name: str, record: str, score: int | None, won: bool) -> str:
    sc = (f'<span class="nfl-score{" win" if won else ""}">{score}</span>'
          if score is not None else "")
    return (f'<div class="nfl-hero-team{" win" if won else ""}">'
            f'<div class="nfl-hero-name">{escape(name)}</div>'
            f'<div class="nfl-hero-rec">{escape(record)}</div>{sc}</div>')


def hero_html(h: NFLHero) -> str:
    result = ""
    if h.away_score is not None and h.home_score is not None:
        result = '<span class="nfl-hero-final">Final</span>'
    return (
        '<div class="nfl-hero">'
        f'<div class="nfl-hero-round">{escape(h.round_label)} · {escape(h.game_date)}</div>'
        '<div class="nfl-hero-teams">'
        f'{_team_col(h.away, h.away_record, h.away_score, h.winner == "away")}'
        f'<div class="nfl-hero-at">at{result}</div>'
        f'{_team_col(h.home, h.home_record, h.home_score, h.winner == "home")}'
        '</div></div>'
    )


def _pct_chip(pct: int | None) -> str:
    if pct is None:
        return ""
    tier = "hi" if pct >= 67 else "lo" if pct <= 33 else "mid"
    return f'<span class="nfl-pct {tier}">{pct}<sup>th</sup></span>'


def identity_html(rows: tuple[NFLIdentityRow, ...], away: str, home: str) -> str:
    if not rows:
        return ""
    head = (f'<div class="nfl-id-row nfl-id-head"><span>{escape(away)}</span>'
            f'<span class="nfl-id-label">Team identity</span><span>{escape(home)}</span></div>')
    body = ""
    for r in rows:
        body += (
            f'<div class="nfl-id-row">'
            f'<span class="nfl-id-val{" better" if r.better == "away" else ""}">'
            f'{escape(r.away_value)} {_pct_chip(r.away_pct)}</span>'
            f'<span class="nfl-id-label">{escape(r.label)}</span>'
            f'<span class="nfl-id-val{" better" if r.better == "home" else ""}">'
            f'{_pct_chip(r.home_pct)} {escape(r.home_value)}</span>'
            f'</div>')
    return f'<div class="nfl-section-head">Team identity <span>(entering this game · league %ile)</span></div><div class="nfl-id">{head}{body}</div>'


def battlefields_html(bfs) -> str:
    if not bfs:
        return ""
    items = ""
    for b in bfs:
        edge_cls = "even" if b.edge == "Even" else "edge"
        items += (
            f'<div class="nfl-bf">'
            f'<div class="nfl-bf-label">{escape(b.label)}</div>'
            f'<div class="nfl-bf-nums"><b>{b.attack}</b> yds/g vs <b>{b.defense}</b> allowed'
            f'<span class="nfl-bf-edge {edge_cls}">{escape(b.edge)}</span></div>'
            f'</div>')
    return f'<div class="nfl-section-head">Battlefields</div><div class="nfl-bfs">{items}</div>'


def _form_col(f: NFLFormLine | None) -> str:
    if f is None:
        return '<div class="nfl-form-col"><div class="nfl-form-dots">—</div></div>'
    dots = "".join(f'<span class="nfl-fdot {"w" if r == "W" else "l"}">{r}</span>'
                   for r in f.results.split())
    return (f'<div class="nfl-form-col"><div class="nfl-form-dots">{dots}</div>'
            f'<div class="nfl-form-sub">{f.ppg:.1f} for · {f.papg:.1f} against (last 5)</div></div>')


def form_html(away: NFLFormLine | None, home: NFLFormLine | None) -> str:
    if away is None and home is None:
        return ""
    return (f'<div class="nfl-section-head">Recent form</div>'
            f'<div class="nfl-form">{_form_col(away)}{_form_col(home)}</div>')


# Only "struggle" is a prediction. The other two states are *stated non-findings*, and
# they are rendered quietly and without a coloured chip so the page never implies a call
# it did not make. See services/nfl_matchup for why there is no "excel".
_MATCHUP_CHIP = {
    "struggle": ("nfl-mx down", "Tough matchup"),
    "favourable-but-flat": ("nfl-mx flat", "Soft on paper"),
    "not-a-factor": ("nfl-mx flat", "Matchup not a factor"),
}


def _matchup_html(call) -> str:
    if call is None or call.direction == "neutral":
        return ""
    css, label = _MATCHUP_CHIP[call.direction]
    swing = ""
    if call.direction == "struggle":
        swing = f'<span class="nfl-mx-swing">{call.swing:+.0f} yds</span>'
    # The receivers' reason is identical for every receiver, so it is stated once for the
    # section instead of repeated four times down the page — four copies of one sentence
    # is vertical space without added value.
    reason = ("" if call.direction == "not-a-factor"
              else f'<div class="nfl-spot-sub">{escape(call.evidence)}</div>')
    return (f'<div class="nfl-spot-mx"><span class="{css}">{escape(label)}</span>{swing}'
            f'{reason}</div>')


def _spot_item(s: NFLSpotlight) -> str:
    badge = ""
    if s.result == "hit":
        badge = f'<span class="nfl-spot-badge hit">✓ {s.actual:g}</span>'
    elif s.result == "miss":
        badge = f'<span class="nfl-spot-badge miss">✗ {s.actual:g}</span>'
    return (
        '<div class="nfl-spot">'
        f'<div class="nfl-spot-top"><span class="nfl-spot-player">{escape(s.player)}'
        f'<span class="nfl-spot-pos">{escape(s.position)}</span></span>{badge}</div>'
        f'<div class="nfl-spot-mkt">{escape(s.market)}</div>'
        f'<div class="nfl-spot-sub">{escape(s.support)}</div>'
        f'{_matchup_html(s.matchup)}</div>'
    )


def _spot_col(title: str, spots: tuple[NFLSpotlight, ...]) -> str:
    items = ("".join(_spot_item(s) for s in spots)
             or '<div class="nfl-spot-sub">No qualifying props.</div>')
    return f'<div class="nfl-spot-col"><div class="nfl-spot-team">{escape(title)}</div>{items}</div>'


def spotlights_html(page: NFLGamePage) -> str:
    if not page.away_spotlights and not page.home_spotlights:
        return ""
    a = page.hero.away.split()[-1]
    h = page.hero.home.split()[-1]
    return (
        '<div class="nfl-section-head">Player spotlights '
        '<span>(pick from prior games · ✓/✗ = result this game · matchup effect is '
        'measured, and only flagged where it is real)</span></div>'
        f'<div class="nfl-spots">{_spot_col(a, page.away_spotlights)}'
        f'{_spot_col(h, page.home_spotlights)}</div>'
    )


def thesis_html(page: NFLGamePage) -> str:
    if not page.thesis:
        return ""
    lines = "".join(f'<li>{escape(s)}</li>' for s in page.thesis)
    return f'<div class="nfl-section-head">The read</div><ul class="nfl-thesis">{lines}</ul>'


def schedule_html(page: NFLGamePage) -> str:
    a, h = page.hero.away.split()[-1], page.hero.home.split()[-1]
    if page.away_rest is None and page.home_rest is None:
        return ""
    def _cell(short, rest):
        return f'<span>{escape(short)} <b>{rest if rest is not None else "—"}d</b> rest</span>'
    note = f'<div class="nfl-rest-note">{escape(page.rest_note)}</div>' if page.rest_note else ""
    return (f'<div class="nfl-section-head">Rest &amp; schedule</div>'
            f'<div class="nfl-rest">{_cell(a, page.away_rest)}{_cell(h, page.home_rest)}</div>{note}')


def page_html(page: NFLGamePage) -> str:
    note = f'<div class="nfl-note">{escape(page.note)}</div>' if page.note else ""
    return (
        hero_html(page.hero)
        + note
        + thesis_html(page)
        + identity_html(page.identity, page.hero.away, page.hero.home)
        + battlefields_html(page.battlefields)
        + spotlights_html(page)
        + form_html(page.away_form, page.home_form)
        + schedule_html(page)
        + '<div class="opp-disclaimer">Preview uses only games before kickoff; the '
          'final score is the actual result. Weather, injuries, and rest are not modeled yet.</div>'
    )
