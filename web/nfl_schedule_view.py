"""Context for the NFL season schedule — by week, or by team.

Two views of one table because they answer different questions: "what is on this
weekend" and "who does my team still have". Both are pure schedule facts.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from src import nfl_schedule


def _kickoff(row) -> str:
    raw = row.get("start_time")
    if not raw:
        return "TBD"
    try:
        when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return "TBD"
    return when.astimezone().strftime("%a %b %-d · %-I:%M %p")


def _day_key(row) -> str:
    raw = row.get("start_time")
    if not raw:
        return "TBD"
    try:
        when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return "TBD"
    return when.astimezone().strftime("%A, %B %-d")


def _game(row, *, show_week: bool = False) -> dict:
    final = (row.get("status") == "post")
    return {
        "game_id": row.get("game_id"), "week": row.get("week"),
        "kickoff": _kickoff(row), "venue": row.get("venue"),
        "away_abbr": row.get("away_abbr"), "home_abbr": row.get("home_abbr"),
        "away_name": row.get("away_name"), "home_name": row.get("home_name"),
        "away_logo": row.get("away_logo"), "home_logo": row.get("home_logo"),
        "away_score": row.get("away_score"), "home_score": row.get("home_score"),
        "final": final, "show_week": show_week,
    }


def _current_week(rows) -> int:
    """The week in progress, or the next one with a game still to come."""
    now = datetime.now(timezone.utc).isoformat()
    upcoming = [r for r in rows if str(r.get("start_time") or "") >= now]
    if upcoming:
        return int(min(upcoming, key=lambda r: str(r["start_time"]))["week"])
    return int(max((r["week"] for r in rows), default=1))


def build_context(params, today: date | None = None, db_path=None) -> dict:
    kwargs = {"db_path": db_path} if db_path else {}
    seasons = nfl_schedule.seasons(**kwargs)
    if not seasons:
        return {"section": "nfl-schedule", "seasons": [], "rows": [], "weeks": [],
                "teams": [], "games": [], "mode": "week", "week": None, "team": None}

    season = seasons[0]
    rows = nfl_schedule.load(season, **kwargs)
    weeks = sorted({int(r["week"]) for r in rows})
    teams = sorted({(r["away_abbr"], r["away_name"]) for r in rows}
                   | {(r["home_abbr"], r["home_name"]) for r in rows})

    team = (params.get("team") or "").upper() or None
    if team and team not in {t[0] for t in teams}:
        team = None

    if team:
        picked = [r for r in rows if team in (r["away_abbr"], r["home_abbr"])]
        games = [_game(r, show_week=True) for r in picked]
        groups = [{"title": f"{team} · {season} season", "games": games}]
        mode, week = "team", None
    else:
        try:
            week = int(params.get("week") or _current_week(rows))
        except (TypeError, ValueError):
            week = _current_week(rows)
        if week not in weeks:
            week = _current_week(rows)
        picked = [r for r in rows if int(r["week"]) == week]
        grouped: dict[str, list] = {}
        for r in picked:
            grouped.setdefault(_day_key(r), []).append(_game(r))
        groups = [{"title": k, "games": v} for k, v in grouped.items()]
        mode = "week"

    return {
        "section": "nfl-schedule", "season": season, "seasons": seasons,
        "weeks": weeks, "teams": teams, "groups": groups,
        "mode": mode, "week": week, "team": team,
        "game_count": sum(len(g["games"]) for g in groups),
    }
