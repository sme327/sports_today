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
    # NFL *can* deep-dive, but only for a game the ingested season feed actually covers.
    # Whether a given game qualifies is decided per game by `deep_dive_available`, so a
    # card never offers a link that lands on "not connected".
    supports_deep_dive = True

    def deep_dive_available(self, game) -> bool:
        from services.nfl_bridge import has_deep_dive
        return has_deep_dive(game)


register(NFLAdapter())
