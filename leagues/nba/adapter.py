"""NBA adapter: schedule-only, via the shared ESPN scoreboard.

Player props + a matchup page (reusing the WNBA basketball foundation) are planned;
until then this surfaces the schedule so NBA games appear on the slate.
"""

from __future__ import annotations

from leagues._espn_schedule import ScheduleOnlyESPN
from leagues.base import register


class NBAAdapter(ScheduleOnlyESPN):
    league = "NBA"
    emoji = "🏀"
    label = "🏀 NBA"
    source_name = "ESPN NBA"
    espn_path = "basketball/nba"
    default_round = "NBA"


register(NBAAdapter())
