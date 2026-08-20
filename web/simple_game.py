"""The matchup page for a league with no player feed.

NCAAF, NHL, NBA and the World Cup arrive as a schedule and nothing else — no play-by-play,
no season feed, no props. The page shows what that honestly supports (records, poll rank,
stakes, the team-level read from `services/editorial.py`) and **states what it cannot
show**, rather than implying a richer page exists elsewhere.

It replaced a stub reading "has not moved to Django yet" — migration scaffolding that
outlived the migration and would have greeted every college-football reader in September.
"""

from __future__ import annotations

from datetime import date

from components.editorial import editorial_empty_html, editorial_html
from components.format import format_game_time
from domain.models import SlateGame
from leagues.base import get_adapter
from services import editorial

# What a schedule alone cannot tell you. Said plainly, because the product rule is that a
# gap is disclosed rather than papered over — and because for these leagues the gap is
# most of what a reader might expect.
_GAPS = ("This league arrives as a schedule only — no play-by-play or season feed is "
         "ingested for it, so there are no player props, no per-player form, and no "
         "efficiency splits. Records and rank are the material; everything above is "
         "built from those alone. Injuries, weather and travel are not modelled.")


def simple_game_context(game: SlateGame, slate_date: date, day: str) -> dict:
    adapter = get_adapter(game.league)
    label = adapter.label if adapter else game.league

    # The read needs a league norm to judge a record against, and a norm needs enough of
    # the league on the slate. Absent that we say so instead of ranking a team against a
    # handful of its peers.
    detail = None
    try:
        from services.daily_feed import load_cached_schedules

        same_league, _status = load_cached_schedules(slate_date).get(game.league, ([], None))
        norm = editorial.league_norms(same_league).get(game.league) if same_league else None
        detail = editorial.interest(game, norm)
    except Exception:                                    # noqa: BLE001
        detail = None

    if detail is not None and detail.signals:
        read = editorial_html(detail)
    else:
        read = editorial_empty_html(
            label,
            "Not enough of this league has played yet for its records to mean anything. "
            "A team is 2-0 on noise until it has four games.",
        )

    score_line = ""
    if game.state in ("live", "final") and game.has_score:
        state = "Final" if game.state == "final" else "Live"
        score_line = (f"{state} · {game.away_display} {game.away_score}, "
                      f"{game.home_display} {game.home_score}")

    return {
        "section": "today", "game": game, "league": game.league, "day": day,
        "league_label": label, "context": game.notable_context or "",
        "start_time": format_game_time(game.start_time),
        "score_line": score_line, "editorial_html": read, "gaps": _GAPS,
    }
