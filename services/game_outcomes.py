"""Did the games we called interesting turn out to be worth watching?

The editorial engine is the only part of the product with no feedback loop. Props are
graded hit/miss every night; a game's interest score has never been checked against
anything, so accumulating slates teaches it nothing. This records what actually
happened so the score can be calibrated the way the prop bands already are.

**What counts as "worth watching" is a proxy, and the honest thing is to record facts
rather than invent a verdict.** Final margin, total score and who won are stored raw;
whether a 1-0 pitchers' duel beat a 12-10 slugfest is not something a number settles,
and nothing here pretends otherwise.

**Leakage.** ESPN's record for a completed game *includes that game* — the Yankees
show 66-51 on a day they won and 66-52 the next. Scoring a past slate straight from
that data would feed the result into the input, and the winner would always look
better than they were. ``pregame_record`` undoes it, so a backfill is scored on what
was knowable at first pitch.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from domain.models import SlateGame
from src.config import DB_PATH

_TABLE = "game_outcomes"
_RECORD_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)(?:\s*-\s*(\d+))?\s*$")


@dataclass(frozen=True)
class GameOutcome:
    slate_date: str
    league: str
    game_id: str
    away: str
    home: str
    interest_score: int
    signals: str            # comma-separated signal kinds, for segmenting later
    margin: int
    total: int
    winner: str | None      # "away" | "home" | None (tie)


def pregame_record(summary: str | None, won: bool | None) -> str | None:
    """A team's record *before* a game, given the record shown after it.

    ESPN's completed-game record already counts that game. Backfilling without
    undoing it leaks the outcome into the input — and always in the same direction,
    since the winner is the one credited.
    """
    if not summary or won is None:
        return summary
    m = _RECORD_RE.match(str(summary))
    if not m:
        return summary
    wins, losses, ties = int(m.group(1)), int(m.group(2)), m.group(3)
    if won and wins > 0:
        wins -= 1
    elif not won and losses > 0:
        losses -= 1
    return f"{wins}-{losses}-{ties}" if ties else f"{wins}-{losses}"


def as_pregame(game: SlateGame) -> SlateGame:
    """A copy of a completed game with both records rewound to first pitch."""
    if game.state != "final" or game.winner is None:
        return game
    import copy
    out = copy.copy(game)
    out.away_record = pregame_record(game.away_record, game.winner == "away")
    out.home_record = pregame_record(game.home_record, game.winner == "home")
    return out


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            slate_date TEXT NOT NULL,
            league TEXT NOT NULL,
            game_id TEXT NOT NULL,
            away TEXT, home TEXT,
            interest_score INTEGER,
            signals TEXT,
            margin INTEGER,
            total INTEGER,
            winner TEXT,
            PRIMARY KEY (slate_date, league, game_id)
        )""")


def outcome_for(game: SlateGame, interest_score: int, signals: list[str]) -> GameOutcome | None:
    """Build a row from a finished game, or None if it is not gradeable."""
    if game.state != "final" or game.away_score is None or game.home_score is None:
        return None
    return GameOutcome(
        slate_date=str(game.start_time.date()) if game.start_time else "",
        league=game.league, game_id=str(game.game_id),
        away=game.away_short or game.away_name or "",
        home=game.home_short or game.home_name or "",
        interest_score=int(interest_score), signals=",".join(sorted(signals)),
        margin=abs(game.away_score - game.home_score),
        total=game.away_score + game.home_score,
        winner=game.winner,
    )


def record(outcomes: list[GameOutcome], db_path: Path = DB_PATH) -> int:
    """Upsert outcomes; returns the number written. Idempotent per game."""
    rows = [o for o in outcomes if o and o.slate_date]
    if not rows:
        return 0
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        conn.executemany(
            f"""INSERT INTO {_TABLE} (slate_date, league, game_id, away, home,
                    interest_score, signals, margin, total, winner)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(slate_date, league, game_id) DO UPDATE SET
                    interest_score=excluded.interest_score, signals=excluded.signals,
                    margin=excluded.margin, total=excluded.total, winner=excluded.winner""",
            [(o.slate_date, o.league, o.game_id, o.away, o.home, o.interest_score,
              o.signals, o.margin, o.total, o.winner) for o in rows])
    return len(rows)


def load(db_path: Path = DB_PATH, league: str | None = None) -> list[dict]:
    """Every recorded outcome, newest first. Empty when the table does not exist."""
    if not Path(db_path).exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            q = f"SELECT * FROM {_TABLE}"
            args: tuple = ()
            if league:
                q += " WHERE league = ?"
                args = (league,)
            return [dict(r) for r in conn.execute(q + " ORDER BY slate_date DESC", args)]
        except sqlite3.OperationalError:
            return []


def calibration(rows: list[dict], league: str | None = None,
                min_games: int = 10) -> dict:
    """Does a higher interest score go with a closer game?

    Reported **within a league**, because a six-point basketball margin and a six-run
    baseball margin are not the same thing. Returns ``{}`` below ``min_games`` rather
    than a number nobody should read.
    """
    sub = [r for r in rows if (league is None or r["league"] == league)
           and r.get("margin") is not None and r.get("interest_score")]
    if len(sub) < min_games:
        return {}
    hi = [r for r in sub if r["interest_score"] >= 60]
    lo = [r for r in sub if r["interest_score"] < 45]
    def _mean(rs, key):
        return round(sum(r[key] for r in rs) / len(rs), 2) if rs else None
    def _close(rs, within):
        return round(sum(1 for r in rs if r["margin"] <= within) / len(rs), 3) if rs else None
    within = 3 if (league or "").upper() != "MLB" else 2
    return {
        "n": len(sub), "league": league or "all",
        "high": {"n": len(hi), "mean_margin": _mean(hi, "margin"), "close_rate": _close(hi, within)},
        "low": {"n": len(lo), "mean_margin": _mean(lo, "margin"), "close_rate": _close(lo, within)},
        "close_within": within,
    }
