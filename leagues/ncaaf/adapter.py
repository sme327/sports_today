"""NCAA Football adapter: schedule-only, via the shared ESPN scoreboard.

Ranked teams show their poll rank (e.g. "#5 Georgia"); the round label carries the
week. No player props (deliberately — NCAA FB's value is games/matchups/upset watch).
"""

from __future__ import annotations

from datetime import date

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

    def deep_dive_available(self, game) -> bool:
        """Week Zero is the deliberate matchup-page dress rehearsal.

        The generic schedule-only gate waits for four games of record history. During
        August we still offer the honest simplified page—schedule, ranks, venue,
        broadcast, and explicit data gaps—so the first live football slate exercises
        navigation and layout before the FBS season begins.
        """
        if game.start_time and game.start_time.month == 8:
            return True
        return super().deep_dive_available(game)

    def scoreboard_groups(self, slate_date: date) -> tuple[str | int, ...]:
        """Include FCS during August's bounded Week Zero dry run.

        Group 80 is FBS and 81 is FCS. Cross-division games can appear in both;
        the shared client unions them by ESPN event id. From September onward the
        product returns to its intentionally FBS-focused slate.
        """
        return (80, 81) if slate_date.month == 8 else ()


register(NCAAFAdapter())
