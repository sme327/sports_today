"""NHL adapter: schedule-only, via the shared ESPN scoreboard.

Player-prop analysis (shots on goal, points, goalie saves) is planned but not built;
until then this surfaces the schedule so hockey nights appear on the slate.
"""

from __future__ import annotations

from leagues._espn_schedule import ScheduleOnlyESPN
from leagues.base import register


class NHLAdapter(ScheduleOnlyESPN):
    league = "NHL"
    emoji = "🏒"
    label = "🏒 NHL"
    source_name = "ESPN NHL"
    espn_path = "hockey/nhl"
    default_round = "NHL"


register(NHLAdapter())
