"""Schedule grid of clickable game cards."""

from __future__ import annotations

from html import escape
from urllib.parse import quote_plus

from components.format import format_game_time, logo_img
from components.navigation import game_href
from domain.models import SlateGame
from leagues.base import get_adapter


def _strength_badge(strength: int | None) -> str:
    """The game's strength score in the upper-right — the top opportunity score among
    its players, so a matchup worth attention is discoverable at a glance. Tiers carry
    meaning beyond color (dim gray → bright white → glowing orange)."""
    if strength is None:
        return ""
    tier = "s3" if strength >= 99 else "s2" if strength >= 92 else "s1"
    return f'<span class="game-strength {tier}">{int(strength)}</span>'


def _top_right(game: SlateGame, strength: int | None) -> str:
    """Upper-right: live/final badge for those states, else the strength score."""
    if game.state == "final":
        return '<span class="game-state final">Final</span>'
    if game.state == "live":
        return '<span class="game-state live"><span class="live-dot"></span>LIVE</span>'
    return _strength_badge(strength)


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


def game_card_html(game: SlateGame, day: str, strength: int | None = None) -> str:
    adapter = get_adapter(game.league)
    away = game.away_display
    home = game.home_display
    away_logo = logo_img(game.away_logo, away, "team-logo")
    home_logo = logo_img(game.home_logo, home, "team-logo")
    time = format_game_time(game.start_time)
    href = game_href(day, game)

    league_label = adapter.label if adapter else game.league
    meta = adapter.describe_game(game) if adapter else (game.venue or "")
    chip = adapter.chip_label if adapter else ""

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
    return (
        f'<a class="game-link" href="{href}" target="_self"><div class="game-card{state_cls}">'
        f'<div class="game-top"><span class="game-top-left">'
        f'<span class="league-name">{escape(league_label)}</span>{time_html}</span>'
        f'{_top_right(game, strength)}</div>'
        f'<div class="teams">'
        f'{_team_row(game, "away", away_logo, away, away_cls)}'
        f'<div class="team-sep">at</div>'
        f'{_team_row(game, "home", home_logo, home, home_cls)}'
        f'</div>'
        f'<div class="game-meta"><span>{escape(meta)}</span>'
        f'<span class="analysis-chip">{escape(chip)}</span></div>'
        f'</div></a>'
    )


def schedule_grid_html(games: list[SlateGame], day: str,
                       scores: dict[str, int] | None = None) -> str:
    scores = scores or {}
    cards = "".join(game_card_html(game, day, scores.get(game.game_id)) for game in games)
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
