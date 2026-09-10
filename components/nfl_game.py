"""NFL matchup-page renderers (pure HTML strings).

The page is built for three depths of reading. Ten seconds: the header and tonight's
matchup. A minute: availability, the read, and the matchup at a glance. Longer: the
players, the props, the form, the roster moves, and the methodology. So the order runs
game → thesis → personnel → strategy → numbers → players → props → supporting detail,
and three layout patterns keep the sections from reading as one stream of identical
boxes: an **editorial** card (full width, one column of prose), a **comparison** (away
left, home right), and a **matchup** (offense → defense).

Colour follows the house rule. Orange marks the few insights that deserve attention
(an observation's dot, an edge, the watch line). Green and coral carry direction only
(over / under, hit / miss, a percentile that is genuinely high or low). Everything
else is grayscale, with weight and size doing the ranking.
"""

from __future__ import annotations

from html import escape

from services.nfl_game_page import (
    NFLFormLine, NFLGamePage, NFLHero, NFLIdentityRow, NFLSpotlight,
)


# --- primitives -----------------------------------------------------------------

def _short_name(name: str) -> str:
    return name.split()[-1]


def _city(name: str) -> str:
    """"New England Patriots" → "New England"; a one-word name stays itself."""
    parts = name.split()
    return " ".join(parts[:-1]) if len(parts) > 1 else name


def _section(kind: str, title: str, subtitle: str, body: str, footnote: str = "") -> str:
    """One major section: an authoritative heading, an optional one-line subtitle saying
    what the section tells you, the body, and an optional muted footnote. ``kind`` is
    the layout pattern (editorial / comparison / matchup / support) and only styles."""
    sub = f'<p class="nfl-sec-sub">{subtitle}</p>' if subtitle else ""
    note = f'<div class="nfl-mx-note">{footnote}</div>' if footnote else ""
    return (f'<section class="nfl-sec nfl-sec--{kind}">'
            f'<header class="nfl-sec-head"><h2 class="nfl-sec-title">{escape(title)}</h2>{sub}</header>'
            f'{body}{note}</section>')


def _two_cols(page: NFLGamePage, render_team) -> str:
    """Away on the left, home on the right — every comparison on the page."""
    return (f'<div class="nfl-cols">{render_team(page.hero.away)}'
            f'{render_team(page.hero.home)}</div>')


def _mark(url: str | None, css: str) -> str:
    """A team mark, or nothing at all — never an empty placeholder box."""
    if not url:
        return ""
    return f'<img class="{css}" src="{escape(url, quote=True)}" alt="" loading="lazy">'


def _logo_for(page: NFLGamePage, team: str) -> str | None:
    h = page.hero
    return h.away_logo if team == h.away else h.home_logo if team == h.home else None


def _col(page: NFLGamePage, team: str, items: str, empty: str = "Nothing listed.") -> str:
    body = items or f'<div class="nfl-empty">{escape(empty)}</div>'
    mark = _mark(_logo_for(page, team), "nfl-col-logo")
    return (f'<div class="nfl-col"><div class="nfl-col-team">{mark}{escape(_short_name(team))}</div>'
            f'<div class="nfl-list">{body}</div></div>')


# --- 1. header ------------------------------------------------------------------

def _team_col(name: str, record: str, score: int | None, won: bool,
              logo: str | None = None) -> str:
    sc = (f'<span class="nfl-score{" win" if won else ""}">{score}</span>'
          if score is not None else "")
    return (f'<div class="nfl-hero-team{" win" if won else ""}">{_mark(logo, "nfl-hero-logo")}'
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
        f'{_team_col(h.away, h.away_record, h.away_score, h.winner == "away", h.away_logo)}'
        f'<div class="nfl-hero-at">at{result}</div>'
        f'{_team_col(h.home, h.home_record, h.home_score, h.winner == "home", h.home_logo)}'
        '</div></div>'
    )


# --- 2. tonight's matchup (hand-authored) -----------------------------------------

def shape_html(page: NFLGamePage) -> str:
    n = page.notes
    if n is None or not (n.shape_headline or n.shape or n.shape_observations):
        return ""
    head = f'<p class="nfl-ed-headline">{escape(n.shape_headline)}</p>' if n.shape_headline else ""
    obs = n.shape_observations or tuple(("", line) for line in n.shape)
    items = "".join(
        f'<li><div class="nfl-ed-lead">{escape(lead)}</div><p class="nfl-ed-text">{escape(text)}</p></li>'
        if lead else f'<li><p class="nfl-ed-text">{escape(text)}</p></li>'
        for lead, text in obs)
    body = f'<ul class="nfl-ed-points">{items}</ul>' if items else ""
    alt = (f'<p class="nfl-ed-alt"><span>The other way.</span> {escape(n.shape_alternative)}</p>'
           if n.shape_alternative else "")
    return _section(
        "editorial", "Tonight's matchup",
        f"The story of the game, written {escape(n.authored)} before any line was posted. "
        "A read, not a forecast.",
        f'<div class="nfl-ed">{head}{body}{alt}</div>')


# --- 3. availability (hand-authored) ---------------------------------------------

_STATUS_ORDER = {"Out": 0, "Doubtful": 1, "Questionable": 2, "PUP": 3, "IR": 4, "Suspended": 5}


def availability_html(page: NFLGamePage) -> str:
    n = page.notes
    if n is None or not n.availability:
        return ""

    def _item(a, impact: bool = False) -> str:
        css = ("q" if a.status in ("Questionable", "Doubtful") else
               "gone" if a.status == "Departed" else "out")
        detail = ""
        if impact and a.impact:
            detail = f'<span class="nfl-avail-impact">{escape(a.impact)}</span>'
        elif a.detail and impact:
            detail = f'<span class="nfl-avail-detail">{escape(a.detail)}</span>'
        return (f'<div class="nfl-avail{" impact" if impact else " minor"}">'
                f'<span class="nfl-avail-name">{escape(a.player)}</span>'
                f'<span class="nfl-pos">{escape(a.position)}</span>'
                f'<span class="nfl-status {css}">{escape(a.status)}</span>{detail}</div>')

    def _team(team: str) -> str:
        mine = [x for x in n.availability if x.team == team]
        report = sorted((a for a in mine if a.status != "Departed"),
                        key=lambda a: _STATUS_ORDER.get(a.status, 9))
        gone = [a for a in mine if a.status == "Departed"]
        # An absence that changes the game is ranked above the rest, with its one line
        # on what it changes; the rest collapse to name and status. If nobody wrote an
        # impact line, every entry is shown the old way — nothing is hidden.
        has_impact = any(a.impact for a in report)
        if has_impact:
            top = [a for a in report if a.impact]
            rest = [a for a in report if not a.impact]
            items = "".join(_item(a, impact=True) for a in top)
            if rest:
                items += ('<div class="nfl-avail-other"><span class="nfl-avail-other-head">Also on '
                          'the report</span>' + "".join(_item(a) for a in rest) + '</div>')
        else:
            items = "".join(_item(a, impact=True) for a in report)
        # Departures are a different fact from tonight's report: not hurt, just no
        # longer here while last season's numbers still count them. Their own rule.
        if gone:
            items += (f'<div class="nfl-avail-gone"><div class="nfl-avail-gone-head">'
                      f'No longer on the roster <span>still in last season\'s numbers</span>'
                      f'</div>{"".join(_item(a) for a in gone)}</div>')
        return _col(page, team, items)

    return _section(
        "comparison", "Availability",
        f"Which absences change tonight's game, from the official report of "
        f"{escape(n.report_date)}. Hand-entered; not in any number on this page.",
        _two_cols(page, _team))


# --- 4. the read (engine) ---------------------------------------------------------

def thesis_html(page: NFLGamePage) -> str:
    """The engine's read as three labelled ideas: each side's case, and what to watch.
    The sentences are the engine's own; the labels are the frame."""
    if not page.thesis:
        return ""
    away, home = page.hero.away, page.hero.home
    a_short, h_short = _short_name(away), _short_name(home)
    ideas: list[tuple[str, str, str]] = []      # (css, label, sentence)
    loose: list[str] = []
    for line in page.thesis:
        prefix, sep, rest = line.partition(": ")
        if sep and prefix == a_short:
            ideas.append(("side", f"{_city(away)} wins if",
                          rest[:1].upper() + rest[1:].replace(" vs ", " beats ", 1)))
        elif sep and prefix == h_short:
            ideas.append(("side", f"{_city(home)} wins if",
                          rest[:1].upper() + rest[1:].replace(" vs ", " beats ", 1)))
        elif sep and prefix == "Watch":
            ideas.append(("watch", "Watch", rest[:1].upper() + rest[1:]))
        else:
            loose.append(line)
    items = "".join(
        f'<div class="nfl-read-idea {css}"><div class="nfl-read-label">{escape(label)}</div>'
        f'<p class="nfl-read-text">{escape(text)}</p></div>'
        for css, label, text in ideas)
    items += "".join(f'<p class="nfl-read-text">{escape(t)}</p>' for t in loose)
    # The expected shape of the game is a person's commitment, not the engine's, and
    # the label says so. It sits with the three ideas because it is their conclusion.
    if page.notes is not None and page.notes.game_script:
        items += (f'<div class="nfl-read-idea script"><div class="nfl-read-label">Expected game '
                  f'script <span>hand-written, a read</span></div>'
                  f'<p class="nfl-read-text">{escape(page.notes.game_script)}</p></div>')
    return _section(
        "editorial", "The read",
        "Each side's case and the swing factor, from last season's profiles. "
        "Records, not forecasts.",
        f'<div class="nfl-read">{items}</div>')


# --- 5. matchup at a glance (engine) ---------------------------------------------

def _pct_chip(pct: int | None) -> str:
    if pct is None:
        return ""
    tier = "hi" if pct >= 67 else "lo" if pct <= 33 else "mid"
    return f'<span class="nfl-pct {tier}">{pct}<sup>th</sup></span>'


def identity_html(rows: tuple[NFLIdentityRow, ...], away: str, home: str) -> str:
    """A compact comparison grid. An even row stays muted; the side with the meaningful
    advantage is brighter, so differences jump out without reading every number."""
    if not rows:
        return ""
    head = (f'<div class="nfl-id-row nfl-id-head"><span>{escape(_short_name(away))}</span>'
            f'<span class="nfl-id-label"></span><span>{escape(_short_name(home))}</span></div>')
    body = ""
    for r in rows:
        even = r.better == "even"
        body += (
            f'<div class="nfl-id-row{" even" if even else ""}">'
            f'<span class="nfl-id-val{" better" if r.better == "away" else ""}">'
            f'{escape(r.away_value)} {_pct_chip(r.away_pct)}</span>'
            f'<span class="nfl-id-label">{escape(r.label)}</span>'
            f'<span class="nfl-id-val{" better" if r.better == "home" else ""}">'
            f'{_pct_chip(r.home_pct)} {escape(r.home_value)}</span>'
            f'</div>')
    return f'<div class="nfl-id">{head}{body}</div>'


def _battle_side(team_short: str, role: str, value: float, unit: str, pct: int | None) -> str:
    return (f'<div class="nfl-bf-side"><div class="nfl-bf-who">{escape(team_short)} '
            f'<span>{escape(role)}</span></div>'
            f'<div class="nfl-bf-val">{value:g} <small>{escape(unit)}</small> {_pct_chip(pct)}</div></div>')


def battlefields_html(bfs, away: str, home: str) -> str:
    """Two large matchup cards — when each team has the ball — each holding its pass and
    rush battlefield. The offense-vs-defense comparison is the fastest way to read the
    game, so it is big and it is not buried."""
    if not bfs:
        return ""
    cards = ""
    for attacker, defender in ((away, home), (home, away)):
        atk, dfn = _short_name(attacker), _short_name(defender)
        rows = ""
        for b in bfs:
            if not b.label.startswith(f"{atk} "):
                continue
            kind = "Passing" if "pass" in b.label else "Rushing"
            edge_cls = "even" if b.edge == "Even" else "edge"
            rows += (f'<div class="nfl-bf-row"><div class="nfl-bf-kind">{kind}</div>'
                     f'{_battle_side(atk, "offense", b.attack, "yds/g", b.attack_pct)}'
                     f'<div class="nfl-bf-arrow" aria-hidden="true">→</div>'
                     f'{_battle_side(dfn, "defense", b.defense, "allowed", b.defense_pct)}'
                     f'<span class="nfl-bf-edge {edge_cls}">{escape(b.edge)}</span></div>')
        cards += (f'<div class="nfl-bf"><div class="nfl-bf-title">When {escape(_city(attacker))} '
                  f'has the ball</div>{rows}</div>')
    return f'<div class="nfl-bfs">{cards}</div>'


def _glance_takeaway(page: NFLGamePage) -> str:
    """One sentence turning the grid into information — description only: who leads
    on more rows, and where the widest gap is. No forecast, no probability."""
    rows = [r for r in page.identity if r.away_pct is not None and r.home_pct is not None]
    if len(rows) < 3:
        return ""
    a, h = _short_name(page.hero.away), _short_name(page.hero.home)
    a_wins = sum(1 for r in rows if r.better == "away")
    h_wins = sum(1 for r in rows if r.better == "home")
    widest = max(rows, key=lambda r: abs(r.away_pct - r.home_pct))
    gap = abs(widest.away_pct - widest.home_pct)
    if gap < 15:
        lead = "These profiles are close on every ranked row"
    elif a_wins >= len(rows) - 1 or h_wins >= len(rows) - 1:
        lead = f"{a if a_wins > h_wins else h} lead on {max(a_wins, h_wins)} of {len(rows)} ranked rows"
    elif a_wins == h_wins:
        lead = f"The teams split the {len(rows)} ranked rows"
    else:
        lead = f"{a if a_wins > h_wins else h} lead on {max(a_wins, h_wins)} of {len(rows)} ranked rows"
    side = a if widest.away_pct > widest.home_pct else h
    return (f'<div class="nfl-glance-say"><span>What it says.</span> {escape(lead)}; the widest '
            f'gap is {escape(widest.label.lower())}, {side} {max(widest.away_pct, widest.home_pct)}th '
            f'against {min(widest.away_pct, widest.home_pct)}th.</div>')


def glance_html(page: NFLGamePage) -> str:
    grid = identity_html(page.identity, page.hero.away, page.hero.home)
    if grid:
        grid += _glance_takeaway(page)
    battles = battlefields_html(page.battlefields, page.hero.away, page.hero.home)
    if not grid and not battles:
        return ""
    joint = ('<div class="nfl-glance-joint">Each offense against the other defense</div>'
             if grid and battles else "")
    return _section(
        "matchup", "Matchup at a glance",
        "Last season's profiles side by side, then each offense against the other defense. "
        "Percentiles are league rank, higher is better for that side.",
        f'<div class="nfl-glance">{grid}{joint}{battles}</div>')


# --- 6. player spotlights (engine) ----------------------------------------------

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
    # section instead of repeated four times down the page.
    reason = ("" if call.direction == "not-a-factor"
              else f'<span class="nfl-spot-why">{escape(call.evidence)}</span>')
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
        f'<div class="nfl-row-top"><span class="nfl-name nfl-name--spot">{escape(s.player)}'
        f'<span class="nfl-pos">{escape(s.position)}</span></span>'
        f'<span class="nfl-row-chips">{badge}</span></div>'
        f'<div class="nfl-spot-thesis">{escape(s.market)}</div>'
        f'<div class="nfl-evidence">{escape(s.support)}</div>'
        f'{_matchup_html(s.matchup)}</div>'
    )


def spotlights_html(page: NFLGamePage) -> str:
    if not page.away_spotlights and not page.home_spotlights:
        return ""
    spots = page.away_spotlights + page.home_spotlights
    footnote = ""
    if any(s.matchup is not None and s.matchup.direction == "not-a-factor" for s in spots):
        footnote = ('Receivers carry no matchup call: across three ingested seasons the gap '
                    'between the softest and toughest defences is about <b>2 receiving '
                    'yards</b>, against a 35-yard game-to-game swing. We measured it rather '
                    'than assuming it.')
    graded = any(s.result is not None for s in spots)
    n = len(spots)
    subtitle = (f"{n} players whose usage sets a bar they usually clear. The bar is picked "
                "from prior games; the matchup effect is measured and flagged only where it "
                "is real" + (" · ✓/✗ is the result in this game." if graded else "."))

    def _team(team: str) -> str:
        mine = page.away_spotlights if team == page.hero.away else page.home_spotlights
        return _col(page, team, "".join(_spot_item(s) for s in mine), "No qualifying props.")

    return _section("comparison", "Player spotlights", subtitle, _two_cols(page, _team), footnote)


# --- 7/8. graded calls (hand-authored) --------------------------------------------

def _lean_item(rank: int, player: str, market: str, direction: str, confidence: str,
               why: str, pre: bool = False) -> str:
    conf = (f'<span class="nfl-conf {confidence}">{escape(confidence)}</span>'
            if confidence and direction != "pass" else "")
    return (
        f'<div class="nfl-lean{" pre" if pre else ""}">'
        f'<div class="nfl-row-top"><span class="nfl-name">'
        f'{f"<span class=nfl-rank>#{rank}</span>" if rank else ""}{escape(player)}</span>'
        f'<span class="nfl-row-chips">{conf}'
        f'<span class="nfl-dir {"pre" if pre else direction}">{escape(direction)}</span></span></div>'
        f'<div class="nfl-market-line">{escape(market)}</div>'
        f'<div class="nfl-why">{escape(why)}</div></div>'
    )


def _graded_section_html(page: NFLGamePage, section: str, title: str, subtitle: str,
                         footnote: str = "", kind: str = "comparison") -> str:
    n = page.notes
    leans = n.in_section(section) if n is not None else ()
    if not leans:
        return ""
    rank = {id(l): i + 1 for i, l in enumerate(leans)}

    def _team(team: str) -> str:
        items = "".join(
            _lean_item(rank[id(l)], l.player, l.market, l.direction, l.confidence, l.why)
            for l in leans if l.team == team)
        return _col(page, team, items, "None on this side.")

    return _section(kind, title, subtitle, _two_cols(page, _team), footnote)


def board_html(page: NFLGamePage) -> str:
    """One board: every posted line evaluated, over / under / pass. The subtitle says
    how many were called out of how many were looked at, because that ratio is what
    makes the calls mean something."""
    n = page.notes
    board = n.in_section("props") if n is not None else ()
    if not board:
        return ""
    called = [l for l in board if l.direction != "pass"]
    subtitle = (f"{len(called)} call{'s' if len(called) != 1 else ''} out of {len(board)} lines "
                f"evaluated, ranked most to least confident across both teams; a pass is a line "
                f"with no edge. A person's calls against the posted lines, not engine output; "
                f'every call is graded in <a href="/leans/">the ledger</a>.')
    # Called lines rank ahead of passes on each side; passes keep the note's order.
    ordered = tuple(called) + tuple(l for l in board if l.direction == "pass")
    rank = {id(l): i + 1 for i, l in enumerate(called)}

    def _team(team: str) -> str:
        items = "".join(
            _lean_item(rank.get(id(l), 0), l.player, l.market, l.direction, l.confidence, l.why)
            for l in ordered if l.team == team)
        return _col(page, team, items, "No lines evaluated on this side.")

    return _section("comparison nfl-sec--leans", "Prop board", subtitle, _two_cols(page, _team),
                    "Why the unders lead: the one matchup effect this project has measured is "
                    "that a tough defence suppresses a player and a soft one does nothing, so a "
                    "matchup can argue for an under and never for an over. An over rests on "
                    "usage alone.")


def falsifiers_html(page: NFLGamePage) -> str:
    """What would change the read: the conditions that test the thesis once the game
    starts. Not another prediction — what to watch to know whether the preview was right."""
    n = page.notes
    if n is None or not n.falsifiers:
        return ""
    items = "".join(
        f'<li><div class="nfl-ed-lead">If {escape(f.condition)}</div>'
        f'<p class="nfl-ed-text">{escape(f.consequence)}</p></li>'
        for f in n.falsifiers)
    return _section(
        "editorial", "What would change the read",
        "The page above is a set of claims. These are the things that would falsify them, "
        "written before kickoff so the game can be watched against them.",
        f'<div class="nfl-ed"><ul class="nfl-ed-points">{items}</ul></div>')


def leans_html(page: NFLGamePage) -> str:
    return _graded_section_html(
        page, "leans", "Prop leans",
        "A person's calls against the posted lines, ranked most to least confident across "
        'both teams. Not engine output; every one is graded in <a href="/leans/">the ledger</a>.',
        "Why the unders lead: the one matchup effect this project has measured is that a "
        "tough defence suppresses a player and a soft one does nothing, so a matchup can "
        "argue for an under and never for an over. An over rests on usage alone.",
        kind="comparison nfl-sec--leans")


def volume_html(page: NFLGamePage) -> str:
    return _graded_section_html(
        page, "volume", "Volume board",
        "Every other posted attempts, completions and receptions line, called. Volume is a "
        'coaching decision the matchup does not touch. Graded in <a href="/leans/">the ledger</a>.',
        kind="comparison nfl-sec--volume")


def overs_html(page: NFLGamePage) -> str:
    return _graded_section_html(
        page, "overs", "Looking for overs",
        "The posted lines where last season's rate beats the price. Usage, never matchup. "
        'Graded in <a href="/leans/">the ledger</a> like the leans.',
        kind="comparison nfl-sec--overs")


def preline_html(page: NFLGamePage) -> str:
    """The read *before* any line existed. No number, so nothing here is graded; the
    chips stay flat so a reader never mistakes it for a call."""
    n = page.notes
    if n is None or not n.preline:
        return ""

    def _team(team: str) -> str:
        items = "".join(
            _lean_item(0, r.player, r.market, r.direction, "", r.why, pre=True)
            for r in n.preline if r.team == team)
        return _col(page, team, items, "Nothing written.")

    # An appendix: what the read was before the market spoke. Interesting after the
    # report, not during it, so it sits last and closed.
    return (f'<details class="nfl-sec nfl-sec--support nfl-sec--appendix">'
            f'<summary class="nfl-sec-head"><h2 class="nfl-sec-title">Before seeing the lines</h2>'
            f'<p class="nfl-sec-sub">What the matchup read suggested before anyone knew what the '
            f'book thought, written {escape(n.authored)}. An anti-bias record: no number, so '
            f'not graded. Open to read.</p></summary>{_two_cols(page, _team)}</details>')


# --- 9. recent form (engine) ------------------------------------------------------

def _form_col(page: NFLGamePage, team: str, f: NFLFormLine | None) -> str:
    if f is None:
        return f'<div class="nfl-form-col"><span class="nfl-col-team">{escape(_short_name(team))}</span><span class="nfl-form-dots">—</span></div>'
    results = f.results.split()
    dots = "".join(f'<span class="nfl-fdot {"w" if r == "W" else "l"}">{r}</span>' for r in results)
    wins = sum(1 for r in results if r == "W")
    record = f"{wins}-{len(results) - wins}"
    mark = _mark(_logo_for(page, team), "nfl-col-logo")
    return (f'<div class="nfl-form-col"><span class="nfl-col-team">{mark}{escape(_short_name(team))}</span>'
            f'<span class="nfl-form-dots">{dots}</span>'
            f'<span class="nfl-form-sub"><b>{record}</b> last {len(results)} · {f.ppg:.1f} for · '
            f'{f.papg:.1f} against</span></div>')


def form_html(page: NFLGamePage) -> str:
    if page.away_form is None and page.home_form is None:
        return ""
    return _section(
        "support", "Recent form", "The last five results, oldest to newest.",
        f'<div class="nfl-form">{_form_col(page, page.hero.away, page.away_form)}'
        f'{_form_col(page, page.hero.home, page.home_form)}</div>')


def schedule_html(page: NFLGamePage) -> str:
    a, h = _short_name(page.hero.away), _short_name(page.hero.home)
    if page.away_rest is None and page.home_rest is None:
        return ""
    def _cell(short, rest):
        return f'<span>{escape(short)} <b>{rest if rest is not None else "—"}d</b> rest</span>'
    note = f'<div class="nfl-rest-note">{escape(page.rest_note)}</div>' if page.rest_note else ""
    return _section("support", "Rest & schedule", "",
                    f'<div class="nfl-rest">{_cell(a, page.away_rest)}{_cell(h, page.home_rest)}</div>{note}')


# --- 10. since last season (hand-authored) ----------------------------------------

def _split_lead(text: str) -> tuple[str, str]:
    """"WR A.J. Brown, by trade from Philadelphia (…)" → the move, then the detail."""
    for sep in (", ", "; ", " ("):
        i = text.find(sep)
        if i > 0:
            return text[:i], text[i:].lstrip(",; ")
    return text, ""


def changes_html(page: NFLGamePage) -> str:
    n = page.notes
    if n is None or not n.changes:
        return ""

    def _team(team: str) -> str:
        items = ""
        for c in (x for x in n.changes if x.team == team):
            lead, detail = _split_lead(c.text)
            detail = f'<span class="nfl-chg-detail">{escape(detail)}</span>' if detail else ""
            items += (f'<div class="nfl-chg"><span class="nfl-chg-dir {c.direction}">{c.direction}</span>'
                      f'<span class="nfl-chg-text"><span class="nfl-chg-lead">{escape(lead)}</span>'
                      f'{detail}</span></div>')
        return _col(page, team, items)

    return _section(
        "support", "Since last season",
        "Who moved. The numbers on this page are last season's; these are the players "
        "they still count, and the ones they cannot see.",
        _two_cols(page, _team))


# --- 11. sources / methodology -----------------------------------------------------

def methodology_html(page: NFLGamePage, disclaimer: str) -> str:
    n = page.notes
    sources = ""
    if n is not None and n.sources:
        links = " · ".join(
            f'<a href="{escape(s.url, quote=True)}" rel="noopener" target="_blank">{escape(s.title)}</a>'
            for s in n.sources)
        sources = f'<p class="nfl-sources">Notes authored {escape(n.authored)}. Sources: {links}</p>'
    return (f'<footer class="nfl-method"><div class="nfl-method-head">Methodology</div>'
            f'<p class="opp-disclaimer">{disclaimer}</p>{sources}</footer>')


# --- the page ---------------------------------------------------------------------

def page_html(page: NFLGamePage) -> str:
    note = f'<div class="nfl-note">{escape(page.note)}</div>' if page.note else ""
    # A pregame page has no result to disclaim; saying "the final score is the actual
    # result" on a game that hasn't kicked off would only confuse.
    played = page.hero.away_score is not None
    disclaimer = ('Preview uses only games before kickoff; the final score is the '
                  'actual result. ' if played else
                  'Preview uses only games already played. ')
    # With a note, injuries *are* on the page — hand-entered, dated, and not in any
    # number. Saying "not modeled yet" alone would read as if they were absent.
    if page.notes is not None:
        disclaimer += (f'Availability and roster changes are hand-entered from the official '
                       f'report of {escape(page.notes.report_date)} and are not modeled in '
                       'the numbers. Weather and rest are not modeled yet.')
    else:
        disclaimer += 'Weather, injuries, and rest are not modeled yet.'
    return (
        hero_html(page.hero)
        + note
        + shape_html(page)            # 2. tonight's matchup
        + availability_html(page)     # 3. availability
        + thesis_html(page)           # 4. the read
        + glance_html(page)           # 5. matchup at a glance
        + spotlights_html(page)       # 6. player spotlights
        + board_html(page)            # 7. the prop board (new notes)
        + leans_html(page)            #    or the three older lists (tonight's note)
        + volume_html(page)
        + overs_html(page)
        + form_html(page)             # 8. recent form
        + schedule_html(page)
        + changes_html(page)          # 9. since last season
        + falsifiers_html(page)       # 10. what would change the read
        + preline_html(page)          #     appendix: before seeing the lines, collapsed
        + methodology_html(page, disclaimer)   # 11. sources / methodology
    )
