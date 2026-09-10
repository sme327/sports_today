"""One NFL game's box score from ESPN's ``summary`` endpoint, reduced to the stats a
prop lean can name — so a hand-written call can be graded the night it settles rather
than waiting a week for the vendor result feed.

Pure parsing is separated from the fetch so the grader is testable offline. Player
identity is the box score's printed name, the same string the note was written against
(`services/nfl_game_notes`); nothing here joins to the ingested feed.
"""

from __future__ import annotations

from typing import Any

import requests

_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary"
_HEADERS = {"User-Agent": "Mozilla/5.0 (sports-today; personal daily companion)"}

# ESPN category → (label → our stat key). "C/ATT" splits into two stats.
_MAP: dict[str, dict[str, str]] = {
    "passing": {"YDS": "passing_yds", "TD": "passing_td", "INT": "passing_int"},
    "rushing": {"CAR": "rushing_att", "YDS": "rushing_yds"},
    "receiving": {"REC": "receptions", "YDS": "receiving_yds"},
}


def _num(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """``{"final": bool, "state": "pre|in|post", "players": {name: {stat: value}}}``.

    A player who appears in *any* category is "in the box score"; a stat he has no
    line for reads as 0.0 (a receiver with no rushing row had zero rushing yards).
    A player absent altogether is absent — the grader voids him, it does not zero him.
    """
    comp = ((payload.get("header") or {}).get("competitions") or [{}])[0]
    status = ((comp.get("status") or {}).get("type") or {})
    state = str(status.get("state") or "")
    players: dict[str, dict[str, float]] = {}
    for team in (payload.get("boxscore") or {}).get("players") or []:
        for cat in team.get("statistics") or []:
            keys = _MAP.get(str(cat.get("name")))
            if not keys:
                continue
            labels = [str(x) for x in cat.get("labels") or []]
            for row in cat.get("athletes") or []:
                name = str((row.get("athlete") or {}).get("displayName") or "").strip()
                if not name:
                    continue
                stats = players.setdefault(name, {})
                for label, raw in zip(labels, row.get("stats") or []):
                    if label == "C/ATT" and cat.get("name") == "passing":
                        comp_att = str(raw).split("/")
                        if len(comp_att) == 2:
                            stats["passing_comp"] = _num(comp_att[0]) or 0.0
                            stats["passing_att"] = _num(comp_att[1]) or 0.0
                    elif label in keys:
                        stats[keys[label]] = _num(raw) or 0.0
    return {"final": bool(status.get("completed")) or state == "post",
            "state": state, "players": players}


def fetch_summary(event_id: str, session: requests.Session | None = None,
                  timeout: float = 20.0) -> dict[str, Any]:
    s = session or requests.Session()
    r = s.get(_SUMMARY, params={"event": event_id}, headers=_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_boxscore(event_id: str, session: requests.Session | None = None) -> dict[str, Any]:
    return parse_summary(fetch_summary(event_id, session))
