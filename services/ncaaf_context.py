"""Season context for college football, where the schedule alone says nothing.

`services/editorial.py` needs four games of record before it will speak, which is right
for a 17-game NFL season and useless for the college opener: on two 0-0 teams it
produces exactly zero signals, and the matchup page falls through to a shrug. This
module supplies what *is* knowable in Week 1, from `src/ncaaf_collector`'s stored data:

- what each team was last season, with the vintage said out loud
- whether the two teams are even in the same division
- whether last season's leading passer is still there, and where he went if not

Everything here is **description, not forecast** — the same rule the editorial signals
follow. "USC were 9-4 in 2025" is a fact about last year, and the caveat that college
rosters turn over hard travels with it rather than being left for the reader to supply.

It emits `editorial.Signal` objects rather than its own HTML so the page renders through
`components/editorial.py` and looks like the rest of the product. Signals are *appended*
to whatever the editorial read produced; by October those records mean something and
this context becomes background rather than the whole page.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from domain.models import SlateGame
from services.editorial import Signal
from src.config import DB_PATH

# The provider's sentinel for "unranked". A literal 99 would otherwise read as a team
# ranked 99th, which is worse than saying nothing.
UNRANKED = 99


@dataclass(frozen=True)
class TeamSeason:
    team_id: str
    name: str | None
    division: str | None
    conference: str | None
    overall: str | None
    wins: int | None
    losses: int | None


@dataclass(frozen=True)
class Passer:
    athlete_id: str | None
    name: str | None
    yards: float | None
    status: str | None            # returning | transferred | inactive | None (unchecked)
    current_team_id: str | None


def _team_id(game: SlateGame, home: bool) -> str | None:
    """SlateGame carries ESPN team ids only in `meta` for these leagues; the adapter
    stores them there rather than widening the model for one league."""
    key = "home_team_id" if home else "away_team_id"
    value = (game.meta or {}).get(key)
    return str(value) if value else None


def load_team_seasons(team_ids: list[str], season: int,
                      db_path: Path = DB_PATH) -> dict[str, TeamSeason]:
    if not team_ids:
        return {}
    marks = ", ".join("?" for _ in team_ids)
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                f"SELECT team_id, team_name, division, conference, overall, wins, losses "
                f"FROM ncaaf_team_seasons WHERE season = ? AND team_id IN ({marks})",
                [season, *team_ids]).fetchall()
    except sqlite3.Error:
        return {}
    return {str(r[0]): TeamSeason(str(r[0]), r[1], r[2], r[3], r[4], r[5], r[6])
            for r in rows}


def load_passers(team_ids: list[str], season: int,
                 db_path: Path = DB_PATH) -> dict[str, Passer]:
    if not team_ids:
        return {}
    marks = ", ".join("?" for _ in team_ids)
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                f"SELECT team_id, athlete_id, athlete_name, passing_yards, status, "
                f"current_team_id FROM ncaaf_team_passers "
                f"WHERE season = ? AND team_id IN ({marks})",
                [season, *team_ids]).fetchall()
    except sqlite3.Error:
        return {}
    return {str(r[0]): Passer(r[1], r[2], r[3], r[4], r[5]) for r in rows}


def team_name(game: SlateGame, home: bool, stored: TeamSeason | None) -> str:
    """Prefer the slate's short name (what the card shows) and fall back to the stored
    one. Poll-rank prefixes are stripped by the caller's own formatting elsewhere; here
    the plain name reads better inside a sentence."""
    short = game.home_short if home else game.away_short
    name = short or (game.home_name if home else game.away_name)
    if name:
        return str(name).lstrip("#0123456789 ").strip() or str(name)
    return (stored.name if stored else None) or "This team"


def _record_phrase(season_row: TeamSeason | None, name: str, season: int) -> str | None:
    if not season_row or not season_row.overall:
        return None
    return f"{name} were {season_row.overall} in {season}"


def last_season_signal(game: SlateGame, seasons: dict[str, TeamSeason],
                       season: int) -> Signal | None:
    """What each side was last year, with the vintage named. The caveat is the point as
    much as the record is."""
    away_id, home_id = _team_id(game, False), _team_id(game, True)
    away, home = seasons.get(away_id or ""), seasons.get(home_id or "")
    if not away and not home:
        return None
    away_name = team_name(game, False, away)
    home_name = team_name(game, True, home)
    parts = [p for p in (_record_phrase(away, away_name, season),
                         _record_phrase(home, home_name, season)) if p]
    if not parts:
        return None
    evidence = tuple(parts)
    missing = [n for n, row in ((away_name, away), (home_name, home)) if not row]
    caveats = [f"A {season} record describes last year's team. College rosters turn "
               f"over hard through the portal and graduation, so this is background, "
               f"not form."]
    if missing:
        caveats.append(f"No {season} record held for {', '.join(missing)}.")
    return Signal("last_season", f"{season} record", "; ".join(parts) + ".",
                  evidence, tuple(caveats))


def division_signal(game: SlateGame, seasons: dict[str, TeamSeason]) -> Signal | None:
    """FBS against FCS. More than half the early-season slate is this game, and it is
    the clearest thing a schedule can tell a reader: it is knowable before kickoff and
    it is usually decisive."""
    away_id, home_id = _team_id(game, False), _team_id(game, True)
    away, home = seasons.get(away_id or ""), seasons.get(home_id or "")
    if not away or not home:
        return None
    if not away.division or not home.division or away.division == home.division:
        return None
    lower = away if away.division == "FCS" else home
    upper = home if lower is away else away
    lower_name = team_name(game, lower is home, lower)
    upper_name = team_name(game, upper is home, upper)
    return Signal(
        "division_gap", "Division mismatch",
        f"{lower_name} play in FCS, a division below {upper_name}.",
        (f"{lower_name}: FCS", f"{upper_name}: FBS"),
        ("These are scheduled as one-sided games and usually are. Expect a "
         "non-competitive result unless something unusual happens.",))


def _passer_sentence(name: str, passer: Passer, opponent_names: dict[str, str],
                     season: int) -> str | None:
    who = passer.name or "Their leading passer"
    yards = f" ({passer.yards:,.0f} yds)" if passer.yards else ""
    if passer.status == "returning":
        return f"{name} return {who}{yards}, their {season} leading passer"
    if passer.status == "transferred":
        where = opponent_names.get(passer.current_team_id or "")
        destination = f" to {where}" if where else " elsewhere"
        return (f"{name} lost {season} leading passer {who}{yards} — "
                f"transferred{destination}")
    if passer.status == "inactive":
        return f"{name} lost {season} leading passer {who}{yards}, no longer on a roster"
    return None


def quarterback_signal(game: SlateGame, passers: dict[str, Passer],
                       destinations: dict[str, str], season: int) -> Signal | None:
    """Whether last season's production is still on the field.

    The single biggest qualifier on a college team's prior-season record: measured over
    30 FBS teams, only nine had their leading passer back. A 9-4 record means something
    different when the quarterback who produced it has gone.
    """
    away_id, home_id = _team_id(game, False), _team_id(game, True)
    lines: list[str] = []
    for team_id, home in ((away_id, False), (home_id, True)):
        passer = passers.get(team_id or "")
        if not passer or not passer.status:
            continue
        name = team_name(game, home, None)
        sentence = _passer_sentence(name, passer, destinations, season)
        if sentence:
            lines.append(sentence)
    if not lines:
        return None
    kept = [ln for ln in lines if " return " in ln]
    label = "QB returns" if len(kept) == len(lines) else "QB turnover"
    return Signal("qb_turnover", label, ". ".join(lines) + ".", tuple(lines),
                  ("Passing yards identify the starter; they do not measure him. A "
                   "returning passer is continuity, not quality.",))


def rank_signal(game: SlateGame) -> Signal | None:
    """A ranked team the editorial read stayed quiet about.

    `editorial._rank_signals` speaks for a lone ranked team only inside the top ten,
    which is the right bar on a full slate and leaves a #14 side unmentioned on an
    opening weekend where it is the most notable thing on the card. This fills that gap
    only; a top-ten team is already covered there and is not repeated here.
    """
    from services.editorial import _RANKED_TOP

    ranks = [(r, home) for r, home in ((game.away_rank, False), (game.home_rank, True))
             if r and r != UNRANKED]
    if not ranks or any(r <= _RANKED_TOP for r, _ in ranks):
        return None
    if len(ranks) == 2:
        return None                     # a ranked pair is the editorial read's own call
    rank, home = ranks[0]
    name = team_name(game, home, None)
    other = team_name(game, not home, None)
    return Signal("ranked_outside_top10", f"#{rank} in action",
                  f"#{rank} {name} face {other}.", (f"#{rank} {name}",))


def occasion_signal(game: SlateGame) -> Signal | None:
    """A named classic, or a game a long way from either campus. Free facts already in
    the scoreboard payload, thrown away until now — a UNC–TCU game played in Dublin is
    a reason to watch and the page said nothing about it."""
    meta = game.meta or {}
    note = (meta.get("event_note") or "").strip()
    city = (meta.get("venue_city") or "").strip()
    country = (meta.get("venue_country") or "").strip()
    state = (meta.get("venue_state") or "").strip()
    where = ", ".join(p for p in (city, state if country in ("", "USA") else country) if p)

    bits: list[str] = []
    if note:
        bits.append(note)
    if game.neutral_site and where:
        bits.append(f"neutral site in {where}")
    elif country and country != "USA" and where:
        bits.append(f"played in {where}")
    if not bits:
        return None
    detail = " · ".join(bits)
    # Short label on purpose: `components/editorial._chips` renders every signal's label
    # as a chip, and "Aer Lingus College Football Classic" as a chip is a line of text
    # pretending to be a tag. The name belongs in the sentence.
    label = "Neutral site" if game.neutral_site else "Occasion"
    return Signal("occasion", label, detail + ".", (detail,))


def signals_for(game: SlateGame, *, prior_season: int,
                db_path: Path = DB_PATH) -> tuple[Signal, ...]:
    """Every context signal available for one game, in reading order.

    Returns an empty tuple when nothing is stored — the caller keeps its honest empty
    state rather than rendering a section that says nothing.
    """
    ids = [i for i in (_team_id(game, False), _team_id(game, True)) if i]
    seasons = load_team_seasons(ids, prior_season, db_path)
    passers = load_passers(ids, prior_season, db_path)

    # Name the transfer destination where we can. The destination is usually not on
    # this card, so it needs its own lookup.
    destination_ids = [p.current_team_id for p in passers.values() if p.current_team_id]
    destinations = {t.team_id: (t.name or t.team_id)
                    for t in load_team_seasons(
                        [d for d in destination_ids if d], prior_season, db_path).values()}

    ordered = (
        last_season_signal(game, seasons, prior_season),
        quarterback_signal(game, passers, destinations, prior_season),
        division_signal(game, seasons),
        rank_signal(game),
        occasion_signal(game),
    )
    return tuple(s for s in ordered if s is not None)
