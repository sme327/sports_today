"""How much a ballpark moves the chance of a hit — as evidence, never as a score.

**Measured, not assumed.** Across 160,963 plate appearances the factor runs 1.13 at
Coors Field to 0.92 at Dodger Stadium, computed against what the *same batting teams*
did elsewhere so team quality cancels out. It survives both checks the method asks for:
split-half correlation +0.589, and 73% of the observed spread is real once the binomial
noise floor is subtracted.

**Why it is only evidence.** Folded into `batter-hit` scoring it widened the quartile
spread and lifted correlation — both intervals clear of zero — but left the top 20%
unmoved, and the top is the only part any surface serves. It failed the ship gate and is
not in the score (decision log, 2026-08-31). Said out loud on the matchup page it costs
nothing and needs no gate, because it changes no ranking and predicts nothing: "hits run
13% above average here" is a fact about games already played, in the same voice as a
team's record.

**Silence is the default.** The true spread between parks is about ±4%, so anything
smaller than that is noise dressed as insight. A park within 5% of neutral gets no note
at all, which is most of them.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from functools import lru_cache
from pathlib import Path

from src.config import DB_PATH

# Below this, the difference is inside the measured noise and gets no note.
_MIN_EFFECT = 0.05
# A park needs a real sample before it says anything about itself.
_MIN_PA = 800


@lru_cache(maxsize=8)
def _factors(as_of_token: str, db_path_token: str) -> dict[str, float]:
    """park (home team) -> factor, from plate appearances strictly before ``as_of``.

    Cached per day: the daily run builds every matchup page in one pass, and this would
    otherwise re-scan the whole feed once per game.
    """
    try:
        with sqlite3.connect(db_path_token) as conn:
            road = dict(conn.execute("SELECT game_id, road_team FROM games"))
            rows = conn.execute(
                "SELECT game_id, batting_team, is_hit FROM plate_appearances "
                "WHERE game_date < ?", (as_of_token,)).fetchall()
    except sqlite3.OperationalError:
        return {}
    if not rows:
        return {}

    teams: dict[str, set] = {}
    for gid, bt, _h in rows:
        teams.setdefault(str(gid), set()).add(bt)
    park_of: dict[str, str] = {}
    for gid, both in teams.items():
        # The home team is the side that is not the road team; its ground is the park.
        r = road.get(int(gid)) if str(gid).lstrip("-").isdigit() else road.get(gid)
        others = [t for t in both if t != r]
        if r and len(both) == 2 and len(others) == 1:
            park_of[gid] = others[0]

    team_hits: dict[str, list] = {}
    cell: dict[tuple, list] = {}
    in_park: dict[str, list] = {}
    for gid, bt, hit in rows:
        park = park_of.get(str(gid))
        if not park:
            continue
        h = int(hit or 0)
        team_hits.setdefault(bt, [0, 0])
        team_hits[bt][0] += h
        team_hits[bt][1] += 1
        cell.setdefault((park, bt), [0, 0])
        cell[(park, bt)][1] += 1
        in_park.setdefault(park, [0, 0])
        in_park[park][0] += h
        in_park[park][1] += 1

    out: dict[str, float] = {}
    for park, (hits, pa) in in_park.items():
        if pa < _MIN_PA:
            continue
        # Expected hits: each visiting side's own rate applied to its plate appearances
        # here. Without this a park inherits the quality of whoever plays in it.
        expected = 0.0
        for (p, bt), (_x, n) in cell.items():
            if p != park:
                continue
            th, tpa = team_hits[bt]
            if tpa:
                expected += n * (th / tpa)
        if expected > 0:
            out[park] = hits / expected
    return out


def note_for(home_team: str | None, as_of: date | None = None,
             db_path: Path = DB_PATH) -> str | None:
    """A one-line, description-only park note, or None when there is nothing to say."""
    if not home_team:
        return None
    token = (as_of or date.today()).isoformat()
    factor = _factors(token, str(db_path)).get(home_team)
    if factor is None or abs(factor - 1.0) < _MIN_EFFECT:
        return None
    pct = round(abs(factor - 1.0) * 100)
    if not pct:
        return None
    direction = "above" if factor > 1 else "below"
    return f"hits run {pct}% {direction} average here"


def clear_cache() -> None:
    _factors.cache_clear()
