"""Schedule grid of clickable game cards."""

from __future__ import annotations

from html import escape
from urllib.parse import quote_plus

from components.format import format_game_time, logo_img
from components.navigation import game_href
from domain.models import SlateGame
from leagues.base import get_adapter
from services.editorial import LeagueNorm, card_signal


def _state_badge(game: SlateGame) -> str:
    """Upper-right badge for live/final; pregame carries nothing there (the strong-
    pick count lives in the footer)."""
    if game.state == "final":
        return '<span class="game-state final">Final</span>'
    if game.state == "live":
        return '<span class="game-state live"><span class="live-dot"></span>LIVE</span>'
    return ""


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
    return f"?day={quote_plus(day)}&focus={quote_plus(str(game.game_id))}#opps"


def _footer(game: SlateGame, day: str, matchup_href: str, count: int,
            threshold: int, deep_dive: bool, norm: LeagueNorm | None = None) -> str:
    """Footer = a strong-pick filter link (left) + a Matchup link (right). Distinct
    treatments: the fire link filters the props below; the pill opens the deep-dive."""
    fire = ""
    if count > 0:
        noun = "prop" if count == 1 else "props"
        fire = (f'<a class="fire-link" target="_self" href="{_focus_href(day, game)}" '
                f'title="Show these props below">🎯 {count} {noun} {threshold}+ →</a>')
    else:
        # No strong props — either the league has none at all, or none cleared the
        # bar today. Either way the slot is empty, so a team-level read earns it.
        signal = card_signal(game, norm)
        if signal:
            fire = (f'<span class="ed-card-signal" title="{escape(signal.detail, quote=True)}">'
                    f'{escape(signal.label)}</span>')
    matchup = (f'<a class="matchup-link" target="_self" href="{matchup_href}">Matchup →</a>'
               if deep_dive else "")
    if not fire and not matchup:
        return ""
    return f'<div class="game-meta">{fire}{matchup}</div>'


def game_card_html(game: SlateGame, day: str, count: int = 0, threshold: int = 90,
                   is_best: bool = False, norm: LeagueNorm | None = None) -> str:
    adapter = get_adapter(game.league)
    away = game.away_display
    home = game.home_display
    away_logo = logo_img(game.away_logo, away, "team-logo")
    home_logo = logo_img(game.home_logo, home, "team-logo")
    time = format_game_time(game.start_time)
    matchup_href = game_href(day, game)
    # Static capability, then a per-game check where the league offers one. NFL can only
    # deep-dive games its season feed covers, and a link that lands on "not connected" is
    # exactly the kind of promise the product rules forbid.
    deep_dive = bool(adapter and getattr(adapter, "supports_deep_dive", False))
    if deep_dive:
        check = getattr(adapter, "deep_dive_available", None)
        if callable(check):
            try:
                deep_dive = bool(check(game))
            except Exception:                       # noqa: BLE001
                deep_dive = False

    league_label = adapter.label if adapter else game.league

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

    # Time sits in the upper-right corner (pregame); live/final show a state badge
    # there instead. Only one of the two is ever present, so the corner is consistent.
    time_html = (f'<span class="game-time">{escape(time)}</span>'
                 if game.state not in ("live", "final") else "")
    # Competition context rides on the existing league line — no extra card height.
    # Only shown when it is notable (playoffs, a football week, a neutral site);
    # ordinary regular-season games say nothing, which is the common case.
    context = game.notable_context
    context_html = (f'<span class="game-context">{escape(context)}</span>'
                    if context else "")
    # Marked per league, never across the slate — see editorial.best_per_league.
    best_html = '<span class="bg-chip">Best game</span>' if is_best else ""
    footer = _footer(game, day, matchup_href, count, threshold, deep_dive, norm)
    # Schedule-only cards (no analysis footer — NFL, World Cup) render compact: the
    # reader just needs to know the game is happening, so it needn't be as tall.
    compact_cls = "" if footer else " game-card--compact"
    # The card body isn't clickable — only the footer links act (filter / deep-dive).
    return (
        f'<div class="game-card{state_cls}{compact_cls}">'
        f'<div class="game-top"><span class="game-top-left">{best_html}'
        f'<span class="league-name">{escape(league_label)}</span>{context_html}</span>'
        f'{time_html}{_state_badge(game)}</div>'
        f'<div class="teams">'
        f'{_team_row(game, "away", away_logo, away, away_cls)}'
        f'<div class="team-sep">at</div>'
        f'{_team_row(game, "home", home_logo, home, home_cls)}'
        f'</div>'
        f'{footer}'
        f'</div>'
    )


def schedule_grid_html(games: list[SlateGame], day: str,
                       counts: dict[str, int] | None = None, threshold: int = 90,
                       best_ids: set[str] | None = None,
                       norms: dict[str, LeagueNorm] | None = None) -> str:
    """``norms`` should be built from the **whole** slate, not this group — the grid is
    rendered once per game state, and a league's shape is not a property of who
    happens to be mid-game."""
    counts = counts or {}
    best_ids = best_ids or set()
    norms = norms or {}
    cards = "".join(game_card_html(game, day, counts.get(game.game_id, 0), threshold,
                                   is_best=str(game.game_id) in best_ids,
                                   norm=norms.get(game.league))
                    for game in games)
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
