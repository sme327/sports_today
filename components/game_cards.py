"""Schedule grid of clickable game cards."""

from __future__ import annotations

from html import escape
from urllib.parse import quote_plus

from components.format import format_game_time, logo_img
from components.navigation import game_href
from domain.models import SlateGame
from leagues.base import get_adapter


def _strength_bars(scores: tuple[int, ...] | None) -> str:
    """A tiny bar chart of the game's top opportunity scores (upper-right). The shape
    shows both frequency (how many strong picks) and distribution (the spread); bars
    ≥ 95 glow orange so a loaded matchup is discoverable at a glance."""
    if not scores:
        return ""
    scores = tuple(scores)[:6]
    n = len(scores)
    w, h, gap = 56.0, 24.0, 3.0
    bw = (w - gap * (n - 1)) / n
    rects = []
    for i, s in enumerate(scores):
        bh = max(2.5, (min(s, 100) - 50) / 50 * h)   # baseline 50 → visible spread
        x, y = i * (bw + gap), h - bh
        cls = "b3" if s >= 95 else "b2" if s >= 85 else "b1"
        rects.append(f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" '
                     f'width="{bw:.1f}" height="{bh:.1f}" rx="1"/>')
    return (f'<span class="game-bars"><svg viewBox="0 0 56 24" preserveAspectRatio="none" '
            f'aria-hidden="true">{"".join(rects)}</svg></span>')


def _top_right(game: SlateGame, bars: tuple[int, ...] | None) -> str:
    """Upper-right: live/final badge for those states, else the strength bar chart."""
    if game.state == "final":
        return '<span class="game-state final">Final</span>'
    if game.state == "live":
        return '<span class="game-state live"><span class="live-dot"></span>LIVE</span>'
    return _strength_bars(bars)


def group_games_by_state(games: list[SlateGame]) -> tuple[list[SlateGame], ...]:
    """Split games into (live, upcoming, final), each chronological.

    League-agnostic: only game state determines placement. Start times are UTC-aware
    or None (None sorts last). Empty groups are simply left empty.
    """
    def _key(g: SlateGame):
        return (g.start_time is None, g.start_time)
    live = sorted((g for g in games if g.state == "live"), key=_key)
    upcoming = sorted((g for g in games if g.state not in ("live", "final")), key=_key)
    final = sorted((g for g in games if g.state == "final"), key=_key)
    return live, upcoming, final


def _score_cell(game: SlateGame, side: str) -> str:
    """A single team's score at the end of its row (live/final only)."""
    if game.state not in ("live", "final") or not game.has_score:
        return ""
    val = game.away_score if side == "away" else game.home_score
    cls = " win" if game.winner == side else " loss" if (game.winner and game.winner != side) else ""
    return f'<span class="team-score{cls}">{val}</span>'


def _team_row(game: SlateGame, side: str, logo: str, name: str, win_cls: str) -> str:
    return (f'<div class="team-row {side}{win_cls}">'
            f'<span class="team-logo-wrap">{logo}</span>'
            f'<span class="team-name">{escape(name)}</span>'
            f'{_score_cell(game, side)}</div>')


def _focus_href(day: str, game: SlateGame) -> str:
    return f"?day={quote_plus(day)}&focus={quote_plus(str(game.game_id))}"


def game_card_html(game: SlateGame, day: str, bars: tuple[int, ...] | None = None) -> str:
    adapter = get_adapter(game.league)
    away = game.away_display
    home = game.home_display
    away_logo = logo_img(game.away_logo, away, "team-logo")
    home_logo = logo_img(game.home_logo, home, "team-logo")
    time = format_game_time(game.start_time)
    matchup_href = game_href(day, game)
    focus_href = _focus_href(day, game)

    league_label = adapter.label if adapter else game.league
    meta = adapter.describe_game(game) if adapter else (game.venue or "")

    # Subtly emphasize the winner (final games only) by dimming the loser's side.
    away_cls = home_cls = ""
    if game.state == "final" and game.winner:
        away_cls = " win" if game.winner == "away" else " loss"
        home_cls = " win" if game.winner == "home" else " loss"

    # State modifier drives the card's color treatment (same layout/size).
    state_cls = ""
    if game.state == "live":
        state_cls = " game-card--live"
    elif game.state == "final":
        state_cls = " game-card--final"

    # Time sits next to the league (game identity), so it's near the matchup; the
    # strength score takes the upper-right on its own.
    time_html = (f'<span class="game-time">{escape(time)}</span>'
                 if game.state not in ("live", "final") else "")
    # The card body links to a props filter for this game; a separate Matchup link
    # opens the deep-dive (two sibling links — never an <a> nested in an <a>).
    return (
        f'<div class="game-card{state_cls}">'
        f'<a class="game-filter-link" href="{focus_href}" target="_self" '
        f'title="Show this game\'s player props below">'
        f'<div class="game-top"><span class="game-top-left">'
        f'<span class="league-name">{escape(league_label)}</span>{time_html}</span>'
        f'{_top_right(game, bars)}</div>'
        f'<div class="teams">'
        f'{_team_row(game, "away", away_logo, away, away_cls)}'
        f'<div class="team-sep">at</div>'
        f'{_team_row(game, "home", home_logo, home, home_cls)}'
        f'</div></a>'
        f'<div class="game-meta"><span>{escape(meta)}</span>'
        f'<a class="matchup-link" href="{matchup_href}" target="_self">Matchup →</a></div>'
        f'</div>'
    )


def schedule_grid_html(games: list[SlateGame], day: str,
                       bars: dict[str, tuple[int, ...]] | None = None) -> str:
    bars = bars or {}
    cards = "".join(game_card_html(game, day, bars.get(game.game_id)) for game in games)
    return f'<div class="schedule-grid">{cards}</div>'


def games_toggle_html(day: str, collapsed: bool, count: int) -> str:
    """A same-tab pill that collapses/expands the schedule grid, sat on the filter
    row (right-aligned). Sticky via the ``games`` query param (carried by the date
    switch; preserved on filter/refresh reruns)."""
    d = quote_plus(day)
    if collapsed:
        noun = "game" if count == 1 else "games"
        return (f'<div class="games-toggle-row"><a class="games-toggle" target="_self" '
                f'href="?day={d}">Show {count} {noun} ▾</a></div>')
    return (f'<div class="games-toggle-row"><a class="games-toggle" target="_self" '
            f'href="?day={d}&games=off">Hide games ▴</a></div>')
