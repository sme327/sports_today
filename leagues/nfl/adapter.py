"""NFL adapter: schedule-only (preseason included), via the shared ESPN scoreboard."""

from __future__ import annotations

from leagues._espn_schedule import ScheduleOnlyESPN
from leagues.base import register


class NFLAdapter(ScheduleOnlyESPN):
    league = "NFL"
    emoji = "🏈"
    label = "🏈 NFL"
    source_name = "ESPN NFL"
    espn_path = "football/nfl"
    with_week = True            # "Preseason · Wk 2"
    default_round = "NFL"


register(NFLAdapter())
