"""Schedule grid of clickable game cards."""

from __future__ import annotations

from html import escape

from components.format import format_game_time, logo_img
from components.navigation import game_href
from domain.models import SlateGame
from leagues.base import get_adapter


def _status_badge(game: SlateGame, time: str) -> str:
    """Top-right of the card: time pill (pre), live badge, or Final badge."""
    if game.state == "final":
        return '<span class="game-state final">Final</span>'
    if game.state == "live":
        return '<span class="game-state live"><span class="live-dot"></span>LIVE</span>'
    return f'<span class="game-time">{escape(time)}</span>'


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


def _center(game: SlateGame) -> str:
    """Center of the teams row: '@' pregame, or the score once it exists."""
    if game.state in ("live", "final") and game.has_score:
        aw = " win" if game.winner == "away" else " loss" if game.winner == "home" else ""
        hw = " win" if game.winner == "home" else " loss" if game.winner == "away" else ""
        return (f'<div class="game-score"><span class="gs{aw}">{game.away_score}</span>'
                f'<span class="gs-sep">–</span><span class="gs{hw}">{game.home_score}</span></div>')
    return '<div class="at-sign">@</div>'


def game_card_html(game: SlateGame, day: str) -> str:
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

    return (
        f'<a class="game-link" href="{href}" target="_self"><div class="game-card{state_cls}">'
        f'<div class="game-top"><span class="league-name">{escape(league_label)}</span>'
        f'{_status_badge(game, time)}</div>'
        f'<div class="teams"><div class="team{away_cls}">{away_logo}<span class="team-name">{escape(away)}</span></div>'
        f'{_center(game)}'
        f'<div class="team home{home_cls}"><span class="team-name">{escape(home)}</span>{home_logo}</div></div>'
        f'<div class="game-meta"><span>{escape(meta)}</span>'
        f'<span class="analysis-chip">{escape(chip)}</span></div>'
        f'</div></a>'
    )


def schedule_grid_html(games: list[SlateGame], day: str) -> str:
    cards = "".join(game_card_html(game, day) for game in games)
    return f'<div class="schedule-grid">{cards}</div>'
