"""Match a live NFL slate game to its row in the ingested vendor feed.

NFL has existed twice in this app and the halves never touched. Today's slate comes from
ESPN and is keyed by ESPN event id (``401873272``); the deep-dive matchup page is built
from Big Data Ball season feeds keyed ``46033-SFO@PHI``. Nothing translated between them,
so clicking a live NFL game got "analysis is not connected yet" while a full page sat one
click away in the archive.

**What joins them is the date and the two teams.** Both sides carry full team names —
ESPN's ``away_name``/``home_name`` and the feed's ``team``/``opponent`` — so this does not
decode ``SFO@PHI`` at all. Names are normalised through the ``nfl_teams`` dimension
(long/short/nick) so a rebrand or a "Football Team" year does not silently break the join.

**Week is deliberately not a join key.** ESPN calls a wild-card game "week 1 of the
postseason"; the feed calls it week 19 of the season. They disagree by design.

**Dates are matched with a one-day window.** ESPN start times are UTC, so a Sunday night
kickoff lands on Monday in UTC while the feed records the local calendar date.

Returning ``None`` is a normal, expected answer — the feed holds regular season and
playoffs only, so **preseason never matches**, and a season nobody has ingested yet never
matches either. Callers must treat "no deep dive" as ordinary rather than an error.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from domain.models import SlateGame
from src.config import DB_PATH

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _key(name: str | None) -> str:
    return _NON_ALNUM.sub("", str(name or "").lower())


@lru_cache(maxsize=4)
def _team_aliases(db: str) -> dict[str, str]:
    """Every spelling of a team we know, mapped to its canonical feed long name.

    Built from the feed's own ``nfl_teams`` dimension, so it stays correct for whatever
    seasons happen to be loaded rather than hard-coding a league roster here.
    """
    out: dict[str, str] = {}
    if not Path(db).exists():
        return out
    try:
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT initial, nfl_initial, long_name, short_name, nick_name FROM nfl_teams")
            for initial, nfl_initial, long_name, short_name, nick in rows:
                canonical = str(long_name or "").strip()
                if not canonical:
                    continue
                for alias in (initial, nfl_initial, long_name, short_name, nick):
                    k = _key(alias)
                    if k:
                        out.setdefault(k, canonical)
    except sqlite3.OperationalError:
        return {}
    return out


def canonical_team(name: str | None, db_path: str | Path = DB_PATH) -> str | None:
    """The feed's long name for a team, however the schedule spelled it."""
    aliases = _team_aliases(str(db_path))
    k = _key(name)
    if not k:
        return None
    if k in aliases:
        return aliases[k]
    # A nickname the dimension didn't list ("Commanders") still resolves if it is the
    # tail of exactly one known team. Ambiguity resolves to nothing, never to a guess.
    hits = {v for a, v in aliases.items() if a.endswith(k) or k.endswith(a)}
    return hits.pop() if len(hits) == 1 else None


def feed_game_id(game: SlateGame, db_path: str | Path = DB_PATH) -> str | None:
    """The vendor ``game_id`` for this slate game, or ``None`` when it is not in the feed.

    ``None`` covers every ordinary case: preseason (the feed carries none), a season not
    yet ingested, a team we cannot resolve, and a genuine absence.
    """
    if game.league != "NFL" or not game.start_time:
        return None
    away = canonical_team(game.away_name or game.away_display, db_path)
    home = canonical_team(game.home_name or game.home_display, db_path)
    if not away or not home or away == home:
        return None
    kickoff = game.start_time.date()
    days = [(kickoff + timedelta(days=d)).isoformat() for d in (0, -1, 1)]
    if not Path(str(db_path)).exists():
        return None
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                f"""SELECT game_id FROM nfl_team_games
                    WHERE game_date IN ({",".join("?" * len(days))})
                      AND venue = 'Home' AND team = ? AND opponent = ?
                    LIMIT 1""",
                (*days, home, away)).fetchone()
    except sqlite3.OperationalError:
        return None
    return str(row[0]) if row else None


def has_deep_dive(game: SlateGame, db_path: str | Path = DB_PATH) -> bool:
    """Whether a real matchup page can be built for this game right now.

    Used to decide whether a card offers a "Matchup →" link at all. Offering one that
    lands on "not connected yet" is the kind of dishonesty the product rules forbid.
    """
    return feed_game_id(game, db_path) is not None


def coverage(db_path: str | Path = DB_PATH) -> dict:
    """What the feed currently holds, for honest UI copy about why a game has no page."""
    if not Path(str(db_path)).exists():
        return {"seasons": [], "latest_date": None}
    try:
        with sqlite3.connect(str(db_path)) as conn:
            seasons = [int(r[0]) for r in conn.execute(
                "SELECT DISTINCT season FROM nfl_team_games WHERE season IS NOT NULL "
                "ORDER BY season")]
            latest = conn.execute("SELECT MAX(game_date) FROM nfl_team_games").fetchone()[0]
    except sqlite3.OperationalError:
        return {"seasons": [], "latest_date": None}
    return {"seasons": seasons, "latest_date": latest}


def unavailable_reason(game: SlateGame, db_path: str | Path = DB_PATH) -> str:
    """One plain sentence on why this game has no deep dive. Never blames the reader."""
    cov = coverage(db_path)
    if not cov["seasons"]:
        return "No NFL season feed has been loaded yet."
    if (game.phase or "").lower() == "preseason":
        return "The season feed covers regular season and playoffs only — not preseason."
    season = game.season
    if season is not None and int(season) not in cov["seasons"]:
        held = ", ".join(str(s) for s in cov["seasons"])
        return (f"The {season} season is not loaded yet — the feed holds {held}. "
                f"Load it with scripts/import_nfl_feed.py.")
    return "This game is not in the loaded season feed."
