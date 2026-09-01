"""When a playoff-race page is worth showing, and when it stops being true.

**The trigger is games remaining, not a date.** A date breaks on a lockout, a shortened
season or a schedule shift, and it has to be re-derived for every league. Games left is
the quantity that actually decides whether a race is legible, it is already on every
standings row, and it moves with the schedule by itself.

**Why the thresholds look so different between sports.** MLB turns on around 30 games
left (~85% of the season played); the NFL around 7 (~65%). That is leverage per game,
not inconsistency: six football games make a two-game deficit close to fatal, while
twenty-five baseball games leave a five-game deficit very much alive. Fraction-complete
would have said those moments were far apart; games-left says they are the same moment.

**Three states, because a season has three.**

``early``  — too much left for the standings to be a race. Nothing to show.
``live``   — inside the window and still being played.
``final``  — the regular season is over. The page **persists through the offseason**
             showing how the race finished, which is a real record, and says so rather
             than pretending the season might still end today.

It leaves when the next season starts: once the standings reset to 0-0 for the new
year the page is hidden again, so last year's race can never sit alongside this year's
games. That reset is the same signal the standings page uses to refuse a table of
thirty-two zeroes.
"""

from __future__ import annotations

# league -> (games in a regular season, games-left threshold to go live)
LEAGUE_WINDOWS: dict[str, tuple[int, int]] = {
    "MLB": (162, 30),     # ~Aug 27
    "NFL": (18, 7),       # after week 11, so week 12 — Thanksgiving
    "NBA": (82, 20),      # ~mid-March
    "NHL": (82, 20),      # ~mid-March
    "WNBA": (44, 12),     # ~mid-August
    "MLS": (34, 8),       # late September, before Decision Day
}


def games_remaining(league: str, wins: int, losses: int, ties: int = 0) -> int:
    total = LEAGUE_WINDOWS.get(league, (0, 0))[0]
    return max(0, total - wins - losses - ties)


def state(league: str, table: dict) -> str:
    """``"early"`` | ``"live"`` | ``"final"`` | ``"preseason"`` for a standings table."""
    season_length, threshold = LEAGUE_WINDOWS.get(league, (0, 0))
    if not table or not season_length:
        return "preseason"

    played = [t.wins + t.losses + t.ties for t in table.values()]
    if not any(played):
        # Every team 0-0: the new season has not started being played yet. This is the
        # off switch — last season's race must not sit beside this season's schedule.
        return "preseason"

    left = [games_remaining(league, t.wins, t.losses, t.ties) for t in table.values()]
    if max(left) == 0:
        return "final"
    # The *fewest* games any contender has left, so a club with games in hand cannot
    # hold the whole page open past the point where the race has resolved for everyone
    # else. Using the maximum would keep it live on one rained-out team.
    return "live" if min(left) <= threshold else "early"


def headline(league: str, window: str) -> tuple[str, str]:
    """(eyebrow, disclaimer) for a state, so a finished race is never worded as a live one."""
    if window == "final":
        return ("How the race finished",
                "Final regular-season standings. This race is over; the page stays up "
                "until the next season begins.")
    return ("If the season ended today",
            "A standings-based snapshot, not playoff odds. Ties and official postseason "
            "tiebreakers are not projected.")
