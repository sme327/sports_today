"""The matchup page for a league with no player feed.

NCAAF, NHL, NBA and the World Cup arrive as a schedule and nothing else — no play-by-play,
no season feed, no props. The page shows what that honestly supports (records, poll rank,
stakes, the team-level read from `services/editorial.py`) and **states what it cannot
show**, rather than implying a richer page exists elsewhere.

It replaced a stub reading "has not moved to Django yet" — migration scaffolding that
outlived the migration and would have greeted every college-football reader in September.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from components.editorial import editorial_empty_html, editorial_html
from components.format import format_game_time, utc_start_iso
from domain.models import SlateGame
from leagues.base import get_adapter
from src.espn_scoreboard import MARKET_LINE_LEAGUES as _MARKET_LINE_LEAGUES
from services import editorial
from services.editorial import GameInterest


def _prior_season(slate_date: date) -> int:
    """The most recent *completed* college season. The season is named for the year it
    starts, so anything from August onward is looking back at last year; January and
    February bowl dates still belong to the season before that."""
    return slate_date.year - 1 if slate_date.month >= 3 else slate_date.year - 2

# What a schedule alone cannot tell you. Said plainly, because the product rule is that a
# gap is disclosed rather than papered over — and because for these leagues the gap is
# most of what a reader might expect.
_GAPS = ("This league arrives as a schedule only — no play-by-play or season feed is "
         "ingested for it, so there are no player props, no per-player form, and no "
         "efficiency splits. Records and rank are the material; everything above is "
         "built from those alone. Injuries, weather and travel are not modelled.")


# College football only, as an experiment (decision log 2026-09-02). This page has the
# least to work with in the whole product — before a record exists, two 0-0 teams produce
# no editorial signals at all — and a spread is the single most information-dense fact
# available about a college game, where talent gaps run to forty points.
#
# It is shown, never used. The number is attributed to the book that set it, phrased in
# ESPN's own words rather than ours, and it reaches no score: `services/editorial` is
# barred from odds by a guard on its source, and a second test asserts the interest score
# is identical whether the line is present or absent.



def _market_line(game: SlateGame) -> dict | None:
    if game.league not in _MARKET_LINE_LEAGUES:
        return None
    line = (game.meta or {}).get("market_line")
    if not isinstance(line, dict) or not line.get("detail"):
        return None
    return line


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

    # College football's opener is the case this page was worst at: two 0-0 teams
    # produce zero editorial signals, so the read was a shrug on every card. The season
    # context supplies what a schedule genuinely supports before a record exists —
    # last season with its vintage named, division mismatch, and whether the passer who
    # produced last season is still there. Appended, not substituted: once records mean
    # something the editorial read leads and this becomes background.
    extra: tuple = ()
    if game.league == "NCAAF":
        try:
            from services import ncaaf_context
            extra = ncaaf_context.signals_for(game, prior_season=_prior_season(slate_date))
        except Exception:                                # noqa: BLE001
            extra = ()

    if detail is not None and (detail.signals or extra):
        detail = replace(detail, signals=detail.signals + extra)
        read = editorial_html(detail)
    elif extra:
        read = editorial_html(GameInterest(score=0, components={}, signals=extra,
                                           caveats=()))
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
        "start_utc": utc_start_iso(game.start_time),
        "score_line": score_line, "editorial_html": read, "gaps": _GAPS,
        "market_line": _market_line(game),
    }
