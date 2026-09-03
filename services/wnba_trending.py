"""League-wide WNBA player trends, in the same shape as the MLB trends page.

Mirrors ``services/mlb_trending`` deliberately: the same row contract, so one template
serves both, and the same discipline — recent form measured against each player's *own*
earlier games rather than a leaderboard of who is simply best.

The three sections are the three markets this project actually scores for the WNBA
(points, rebounds, assists), because a trend the site cannot act on is decoration.

**Description, not forecast.** A player scoring more lately is a record of games already
played. Nothing here says it continues — the same rule the MLB page follows, and for the
same reason: form is a weak predictor, and a page implying otherwise would contradict the
scorers.

**Bounded by the slate.** Only games strictly before ``as_of`` are read.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from src.config import DB_PATH

_ACTIVE_WITHIN_DAYS = 10
_MIN_GAMES = 10          # enough that "recent" and "earlier" are both real samples
_RECENT = 5
_LIMIT = 6

# What counts as a move worth showing, per game. Set from each market's own spread
# rather than one shared number: three assists is a transformation, three points is a
# quiet night.
_MARKETS = (
    ("points", "points", "Points", "Scoring", 4.0,
     "Who is scoring more—or less—than they were."),
    ("rebounds", "rebounds", "Rebounds", "Rebounding", 2.0,
     "Where the glass work has shifted most."),
    ("assists", "assists", "Assists", "Playmaking", 1.5,
     "Who is creating more—or less—for team-mates."),
)


def _row(*, player_id, name, team, headshot, sort, primary, change, direction, baseline):
    """The same row shape MLB emits, so one template serves both leagues.

    Adding a metric is a declaration — a title, a window, a display type and rows — not
    a new component, which is the whole point of the shape being shared.
    """
    return {"player_id": str(player_id), "name": name, "team": team,
            "headshot": headshot, "sort": sort, "primary": primary, "unit": "",
            "change": change, "direction": direction, "baseline": baseline}


def _load(as_of: date, db_path: Path):
    import pandas as pd

    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT player_id, player_name, team, headshot, game_id, game_date, "
            "minutes, points, rebounds, assists FROM wnba_player_game_logs "
            "WHERE substr(game_date, 1, 10) < ?",
            conn, params=(as_of.isoformat(),))
    return df


def build_context(as_of: date | None = None, db_path: Path = DB_PATH) -> dict:
    import pandas as pd

    today = as_of or date.today()
    try:
        df = _load(today, db_path)
    except Exception:
        df = pd.DataFrame()
    sections = []
    through = None

    if not df.empty:
        df["d"] = df["game_date"].astype(str).str[:10]
        # A logged row with no minutes is a player who did not take the floor; counting
        # it as a zero would manufacture a slump out of a healthy scratch.
        df = df[pd.to_numeric(df["minutes"], errors="coerce").fillna(0) > 0]

    if not df.empty:
        # A real date, not the ISO string: the template formats this with |date, which
        # renders a string as nothing at all — silently, and only on this page.
        through = date.fromisoformat(df["d"].max())
        cutoff = (today - timedelta(days=_ACTIVE_WITHIN_DAYS)).isoformat()
        df = df.sort_values("d")
        by_player = {pid: g for pid, g in df.groupby("player_id")}

        for slug, column, market, title, threshold, read in _MARKETS:
            cards = []
            for pid, group in by_player.items():
                if len(group) < _MIN_GAMES or group["d"].iloc[-1] < cutoff:
                    continue
                values = pd.to_numeric(group[column], errors="coerce").fillna(0).tolist()
                recent, prior = values[-_RECENT:], values[:-_RECENT]
                if len(prior) < _RECENT:
                    continue
                recent_avg = sum(recent) / len(recent)
                prior_avg = sum(prior) / len(prior)
                delta = recent_avg - prior_avg
                if abs(delta) < threshold:
                    continue
                cards.append(_row(
                    player_id=pid,
                    name=str(group["player_name"].iloc[-1]),
                    team=str(group["team"].iloc[-1]),
                    headshot=str(group["headshot"].iloc[-1] or ""),
                    sort=abs(delta), primary=f"{recent_avg:.1f}",
                    change=f"{delta:+.1f}",
                    direction="up" if delta > 0 else "down",
                    baseline=f"{prior_avg:.1f}"))
            cards.sort(key=lambda c: c["sort"], reverse=True)
            sections.append({
                "slug": slug, "display": "comparison", "title": title,
                "subtitle": read, "nav": title,
                "context": f"Last {_RECENT} games vs earlier sample",
                "columns": (f"{market} per game, last {_RECENT}", "Change", "Before"),
                "rows": cards[:_LIMIT]})

    return {"section": "trending", "league": "WNBA", "sections": sections,
            "through": through, "has_data": any(s["rows"] for s in sections)}
