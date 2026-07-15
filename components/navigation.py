"""Same-tab query-parameter navigation helpers.

All internal links stay in the same browser tab (``target="_self"``) and encode
navigation purely in query parameters (``day``, ``league``, ``game``), matching
the app's existing model.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from domain.models import SlateGame


def day_label(day: str) -> str:
    return "Tomorrow" if day == "tomorrow" else "Today"


def day_possessive(day: str) -> str:
    return "Tomorrow’s" if day == "tomorrow" else "Today’s"


def game_href(day: str, game: SlateGame) -> str:
    return (
        f"?day={quote_plus(day)}"
        f"&league={quote_plus(game.league)}"
        f"&game={quote_plus(str(game.game_id))}"
    )


def back_href(day: str) -> str:
    return f"?day={quote_plus(day)}"
