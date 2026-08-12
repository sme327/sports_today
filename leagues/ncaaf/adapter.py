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
    # Deliberately no `espn_groups`: the default returns FBS, which is what this product
    # means by "college football". Adding FCS (group 81) is possible and would take a
    # November Saturday from 45 games to 99 — complete, but mostly lower-division games a
    # reader did not ask for. Revisit only alongside a curation gate.
    with_week = True            # "Week 1"
    rank_prefix = True          # "#5 Georgia"
    default_round = "College Football"


register(NCAAFAdapter())
