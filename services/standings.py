"""Reading standings for the surfaces that need a reference point.

**The gap this fills.** An MLB matchup page describes *how* a team plays — power,
contact, plate discipline, speed — and never says whether they are any good. Two slider
stacks give a reader nothing to convert into wins, because nothing on the page is
denominated in wins. A record and a division position are that anchor.

It is deliberately description, not forecast: the same rule the editorial signals follow.
"71-66, 2nd in NL Central, 4.5 GB" is a fact about games already played. It says nothing
about tonight, and the wording must never imply it does.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.config import DB_PATH
from src.standings_store import load

# "American League East" -> "AL East". Long division names crowd a hero line that
# already carries a record; the short form is what every scoreboard uses.
_CONFERENCE_ABBR = {
    "American League": "AL",
    "National League": "NL",
    "Eastern Conference": "East",
    "Western Conference": "West",
}


@dataclass(frozen=True)
class TeamStanding:
    team_id: str
    team_name: str | None
    division: str | None
    division_rank: int | None
    wins: int
    losses: int
    ties: int
    games_behind: float | None
    streak: str | None
    last_ten: str | None
    win_pct: float | None = None
    logo: str | None = None

    @property
    def record(self) -> str:
        """"82-54", or "9-6-1" in a sport with ties."""
        base = f"{self.wins}-{self.losses}"
        return f"{base}-{self.ties}" if self.ties else base

    @property
    def division_short(self) -> str | None:
        if not self.division:
            return None
        for full, abbr in _CONFERENCE_ABBR.items():
            if self.division.startswith(full):
                rest = self.division[len(full):].strip()
                return f"{abbr} {rest}".strip() if rest else abbr
        return self.division

    @property
    def place(self) -> str | None:
        """"1st in AL East" / "2nd in AL Central, 3.5 GB"."""
        if not self.division_rank or not self.division_short:
            return None
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(
            self.division_rank if self.division_rank < 20 else 0, "th")
        if self.division_rank in (11, 12, 13):
            suffix = "th"
        place = f"{self.division_rank}{suffix} in {self.division_short}"
        # The leader's own games back is zero and saying "0.0 GB" of a team that leads
        # reads as a deficit. Only a chaser gets the number.
        if self.games_behind and self.games_behind > 0:
            gb = f"{self.games_behind:g}"
            return f"{place}, {gb} GB"
        return place

    @property
    def summary(self) -> str:
        """The one-line anchor: record first, position second."""
        return f"{self.record} · {self.place}" if self.place else self.record


def for_league(league: str, as_of: date | None = None,
               db_path: Path = DB_PATH) -> dict[str, TeamStanding]:
    """team_id -> standing, as it stood on ``as_of`` (default: latest stored).

    The date bound is the project's ``as_of`` rule: a matchup page rebuilt in October
    must describe an August game with August's records, not today's.
    """
    snapshot = _snapshot_for(league, as_of, db_path)
    if as_of is not None and snapshot is None:
        # "No standings at or before that date" and "no date given" are different
        # questions with the same `None`, and collapsing them let a page for an
        # early-season slate fall through to *today's* standings — precisely the leak
        # the as_of bound exists to stop. Absent stays absent.
        return {}
    rows = load(league, snapshot, db_path)
    out: dict[str, TeamStanding] = {}
    for row in rows:
        out[str(row["team_id"])] = TeamStanding(
            team_id=str(row["team_id"]), team_name=row.get("team_name"),
            division=row.get("division"), division_rank=row.get("division_rank"),
            wins=row.get("wins") or 0, losses=row.get("losses") or 0,
            ties=row.get("ties") or 0, games_behind=row.get("games_behind"),
            streak=row.get("streak"), last_ten=row.get("last_ten"),
            win_pct=row.get("win_pct"), logo=row.get("logo"),
        )
    return out


def _snapshot_for(league: str, as_of: date | None, db_path: Path) -> str | None:
    if as_of is None:
        return None
    import sqlite3

    from src.standings_store import latest_snapshot

    with sqlite3.connect(db_path) as conn:
        try:
            return latest_snapshot(conn, league, as_of.isoformat())
        except sqlite3.OperationalError:
            return None


def pair_for(league: str, away_id: str | None, home_id: str | None,
             as_of: date | None = None,
             db_path: Path = DB_PATH) -> tuple[TeamStanding | None, TeamStanding | None]:
    """Both sides of a matchup, or Nones where a team is not in the table.

    Joined on team id, never name — the league's own ids, from the same source that
    schedules it (StatsAPI for MLB, ESPN elsewhere).
    """
    table = for_league(league, as_of, db_path)
    return table.get(str(away_id or "")), table.get(str(home_id or ""))
