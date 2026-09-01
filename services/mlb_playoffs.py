"""A factual MLB playoff-race view: current field, bubble, and consequential games."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from services import playoff_window, standings
from src.config import DB_PATH
from src.mlb_api import schedule_range


def _gb(team, cutoff) -> float:
    return ((cutoff.wins - team.wins) + (team.losses - cutoff.losses)) / 2


def _short_conference(value: str | None) -> str:
    return "AL" if value == "American League" else "NL" if value == "National League" else (value or "MLB")


def _race_rows(table: dict) -> tuple[list[dict], dict[str, dict]]:
    conferences: dict[str, list] = {}
    for team in table.values():
        conferences.setdefault(team.conference or "MLB", []).append(team)
    panels, status_by_id = [], {}
    for conference, teams in sorted(conferences.items()):
        leaders = [t for t in teams if t.division_rank == 1]
        leaders.sort(key=lambda t: (t.win_pct or 0, t.wins), reverse=True)
        others = [t for t in teams if t.division_rank != 1]
        others.sort(key=lambda t: (t.win_pct or 0, t.wins), reverse=True)
        cutoff = others[2] if len(others) >= 3 else None
        projected = leaders + others[:3]
        rows = []
        for seed, team in enumerate(projected, 1):
            label = "Division leader" if team in leaders else f"Wild Card {others.index(team) + 1}"
            row = _team_row(team, seed=seed, status=label, gap="In position")
            rows.append(row)
            status_by_id[team.team_id] = {"conference": conference, "division": team.division,
                                          "gap": 0.0, "status": label, "in_field": True}
        bubble = []
        if cutoff:
            for team in others[3:]:
                gap = max(0.0, _gb(team, cutoff))
                if gap <= 8:
                    row = _team_row(team, status=f"{gap:g} GB of Wild Card", gap=f"{gap:g} GB")
                    bubble.append(row)
                    status_by_id[team.team_id] = {"conference": conference, "division": team.division,
                                                  "gap": gap, "status": row["status"], "in_field": False}
        panels.append({"name": _short_conference(conference), "field": rows, "bubble": bubble})
    return panels, status_by_id


def _team_row(team, *, seed=None, status: str, gap: str) -> dict:
    return {"id": team.team_id, "seed": seed, "name": team.team_name, "logo": team.logo,
            "record": team.record, "status": status, "gap": gap,
            "remaining": playoff_window.games_remaining(
                "MLB", team.wins, team.losses, team.ties),
            "streak": team.streak or ""}


def _rival_meetings(games: list[dict], status: dict[str, dict]) -> dict[str, int]:
    """Remaining games against the teams a club is actually racing.

    "Games remaining" alone does not say who they are against, and 24 games against the
    field is a different September from 24 against the basement. A club's rivals are the
    other clubs in its own conference's field and bubble — the set it can still gain or
    lose ground on directly.

    This is schedule arithmetic, not a projection: every one of these games is on the
    calendar today. It says nothing about who wins them, which is the line the rest of
    this page holds too.
    """
    by_conference: dict[str, set] = {}
    for team_id, meta in status.items():
        by_conference.setdefault(meta["conference"], set()).add(str(team_id))

    counts: dict[str, int] = {tid: 0 for tid in status}
    for game in games:
        if game.get("phase") != "regular" or game.get("state") == "final":
            continue
        away, home = str(game.get("away_id") or ""), str(game.get("home_id") or "")
        a, h = status.get(away), status.get(home)
        if not a or not h or a["conference"] != h["conference"]:
            continue
        rivals = by_conference.get(a["conference"], set())
        if away in rivals and home in rivals:
            counts[away] += 1
            counts[home] += 1
    return counts


def _important_games(games: list[dict], status: dict[str, dict]) -> list[dict]:
    ranked = []
    for game in games:
        if game.get("phase") != "regular" or game.get("state") == "final":
            continue
        away, home = status.get(str(game.get("away_id"))), status.get(str(game.get("home_id")))
        if not away and not home:
            continue
        score = 0.0
        for side in (away, home):
            if side:
                score += 7 if side["in_field"] else max(0, 7 - side["gap"])
        same_conf = bool(away and home and away["conference"] == home["conference"])
        same_div = bool(same_conf and away["division"] == home["division"])
        if same_conf:
            score += 3
        if same_div:
            score += 4
        if score < 7:
            continue
        if same_div:
            why = f"Direct {away['division'].replace('American League', 'AL').replace('National League', 'NL')} race."
        elif same_conf:
            why = f"Both clubs are part of the {_short_conference(away['conference'])} playoff picture."
        else:
            side = away or home
            club = game.get("away_short") if away else game.get("home_short")
            why = f"{club} is {side['status'].lower()}."
        try:
            start = datetime.fromisoformat(str(game.get("game_date")).replace("Z", "+00:00"))
            day = start.strftime("%a, %b %-d")
        except (TypeError, ValueError):
            day = str(game.get("game_date") or "")[:10]
        ranked.append((score, str(game.get("game_date") or ""), {
            "game_id": game.get("game_pk"), "day": day,
            "away": game.get("away_short") or game.get("away"),
            "home": game.get("home_short") or game.get("home"),
            "away_logo": game.get("away_logo"), "home_logo": game.get("home_logo"),
            "why": why,
        }))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:8]]


def build_context(as_of: date | None = None, db_path: Path = DB_PATH,
                  schedule_fetcher: Callable = schedule_range) -> dict:
    today = as_of or date.today()
    table = standings.for_league("MLB", today, db_path=db_path)

    # Before the window there is no race to describe, and once the next season starts
    # last year's is not a race either. Both states render nothing rather than a page
    # that quietly misdates itself.
    window = playoff_window.state("MLB", table)
    if window in ("early", "preseason"):
        return {"section": "playoffs", "league": "MLB", "panels": [], "games": [],
                "schedule_available": True, "window_end": None, "as_of": today,
                "has_data": False, "window": window,
                "eyebrow": playoff_window.headline("MLB", window)[0],
                "disclaimer": playoff_window.headline("MLB", window)[1]}

    panels, status = _race_rows(table)
    end = today + timedelta(days=14)
    # The regular season ends in the first days of October; asking to the end of the
    # month costs nothing and means the head-to-head count is the *whole* run-in rather
    # than a fortnight of it.
    season_end = date(today.year, 10, 31)
    schedule, schedule_available = [], True
    try:
        schedule = schedule_fetcher(today, max(end, season_end))
    except Exception:
        schedule_available = False

    meetings = _rival_meetings(schedule, status) if schedule else {}
    for panel in panels:
        for row in (*panel["field"], *panel["bubble"]):
            row["vs_rivals"] = meetings.get(str(row["id"]))

    in_window = [g for g in schedule
                 if str(g.get("date") or g.get("game_date") or "")[:10] <= end.isoformat()] \
        if schedule else []
    eyebrow, disclaimer = playoff_window.headline("MLB", window)
    return {"section": "playoffs", "league": "MLB", "panels": panels,
            "window": window, "eyebrow": eyebrow, "disclaimer": disclaimer,
            "games": _important_games(in_window or schedule, status),
            "schedule_available": schedule_available,
            "window_end": end, "as_of": today, "has_data": bool(table)}
