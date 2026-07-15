"""LeagueAdapter protocol and registry.

Adapters translate a league's raw feed into the shared domain models and expose a
uniform opportunity interface. The degraded-mode league-wide ranking is an
explicit ``mode`` (owner refinement, section 3.3), never an accidental byproduct
of a missing schedule.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, Protocol, runtime_checkable

from domain.models import Opportunity, OpportunityMode, SlateGame


@runtime_checkable
class LeagueAdapter(Protocol):
    league: str          # canonical code, e.g. "MLB"
    emoji: str           # e.g. "⚾️"
    label: str           # filter-chip label, e.g. "⚾️ MLB"
    source_name: str     # provenance label, e.g. "MLB StatsAPI"
    supports_deep_dive: bool
    chip_label: str      # game-card chip, e.g. "Analysis"

    def describe_game(self, game: SlateGame) -> str:
        """One-line game-card meta (probable pitchers, venue, round, ...)."""
        ...

    def fetch_schedule(self, slate_date: date) -> list[SlateGame]:
        """Fetch and normalize the league's games for ``slate_date``.

        May raise on network/parse failure; the schedules service turns that into
        a cached/degraded status.
        """
        ...

    def match_team(self, identifier: str | None) -> str | None:
        """Return a canonical team key for any name/abbr/id, or None."""
        ...

    def opportunities(
        self,
        *,
        as_of: date,
        scheduled_team_ids: Iterable[str] | None = None,
        mode: OpportunityMode = OpportunityMode.SLATE,
        limit: int = 8,
    ) -> list[Opportunity]:
        """Ranked opportunities using only data strictly before ``as_of``.

        ``mode=SLATE`` restricts to ``scheduled_team_ids``; ``mode=LEAGUE_WIDE`` is
        the explicit degraded fallback across all teams.
        """
        ...


_REGISTRY: dict[str, LeagueAdapter] = {}
# Preserve intended display order (MLB, WNBA, World Cup, then future leagues).
_ORDER: list[str] = []


def register(adapter: LeagueAdapter) -> LeagueAdapter:
    _REGISTRY[adapter.league] = adapter
    if adapter.league not in _ORDER:
        _ORDER.append(adapter.league)
    return adapter


def get_adapter(league: str) -> LeagueAdapter | None:
    return _REGISTRY.get(league)


def iter_adapters() -> list[LeagueAdapter]:
    return [_REGISTRY[name] for name in _ORDER if name in _REGISTRY]
