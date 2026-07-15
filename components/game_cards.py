"""Schedule grid of clickable game cards."""

from __future__ import annotations

from html import escape

from components.format import format_game_time, logo_img
from components.navigation import game_href
from domain.models import SlateGame
from leagues.base import get_adapter


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

    return (
        f'<a class="game-link" href="{href}" target="_self"><div class="game-card">'
        f'<div class="game-top"><span class="league-name">{escape(league_label)}</span>'
        f'<span class="game-time">{escape(time)}</span></div>'
        f'<div class="teams"><div class="team">{away_logo}<span class="team-name">{escape(away)}</span></div>'
        f'<div class="at-sign">@</div>'
        f'<div class="team home"><span class="team-name">{escape(home)}</span>{home_logo}</div></div>'
        f'<div class="game-meta"><span>{escape(meta)}</span>'
        f'<span class="analysis-chip">{escape(chip)}</span></div>'
        f'</div></a>'
    )


def schedule_grid_html(games: list[SlateGame], day: str) -> str:
    cards = "".join(game_card_html(game, day) for game in games)
    return f'<div class="schedule-grid">{cards}</div>'
