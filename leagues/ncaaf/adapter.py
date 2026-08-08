"""NCAA Football adapter: schedule-only, via the shared ESPN scoreboard.

Ranked teams show their poll rank (e.g. "#5 Georgia"); the round label carries the
week. No player props (deliberately — NCAA FB's value is games/matchups/upset watch).
"""

from __future__ import annotations

from leagues._espn_schedule import ScheduleOnlyESPN
from leagues.base import register


class NCAAFAdapter(ScheduleOnlyESPN):
    league = "NCAAF"
    emoji = "🏈"
    label = "🏈 NCAAF"
    source_name = "ESPN College Football"
    espn_path = "football/college-football"
    with_week = True            # "Week 1"
    rank_prefix = True          # "#5 Georgia"
    default_round = "College Football"


register(NCAAFAdapter())
