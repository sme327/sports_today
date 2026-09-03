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
    """Two races per league, kept apart, because they are two different questions.

    Winning a division is a contest against four named clubs and carries an automatic
    place. The Wild Card is a separate contest among everyone who does not win one. A
    club can be two games back in its division *and* holding a Wild Card at the same
    time — one table showing only its Wild Card standing says nothing about the race it
    is actually in, and the page was doing exactly that.

    So each league gets its division races, then its Wild Card race. A club appears in
    both when it is genuinely in both.
    """
    conferences: dict[str, list] = {}
    for team in table.values():
        conferences.setdefault(team.conference or "MLB", []).append(team)

    panels, status_by_id = [], {}
    for conference, teams in sorted(conferences.items()):
        short = _short_conference(conference)

        # --- the division races -------------------------------------------------
        divisions: dict[str, list] = {}
        for team in teams:
            divisions.setdefault(team.division or short, []).append(team)
        division_panels, leaders = [], []
        for name, clubs in sorted(divisions.items()):
            clubs = sorted(clubs, key=lambda t: (t.win_pct or 0, t.wins), reverse=True)
            leaders.append(clubs[0])
            rows = []
            for place, club in enumerate(clubs, 1):
                gap = max(0.0, _gb(club, clubs[0]))
                rows.append(_team_row(
                    club, seed=place,
                    status="Leads the division" if place == 1 else f"{gap:g} GB in the division",
                    # Bare number: the division card states "GB" in its heading, so
                    # repeating it on five rows only narrows the column it sits in.
                    gap="—" if place == 1 else f"{gap:g}"))
            division_panels.append({"name": name.replace("American League", "AL")
                                                .replace("National League", "NL"),
                                    "teams": rows})

        # --- the Wild Card race, which is everyone who is not leading one --------
        others = sorted((t for t in teams if t not in leaders),
                        key=lambda t: (t.win_pct or 0, t.wins), reverse=True)
        cutoff = others[2] if len(others) >= 3 else None
        wc_field, wc_bubble = [], []
        for i, club in enumerate(others[:3], 1):
            wc_field.append(_team_row(club, seed=i, status=f"Wild Card {i}",
                                      gap="In position"))
        if cutoff:
            for club in others[3:]:
                gap = max(0.0, _gb(club, cutoff))
                if gap <= 8:
                    wc_bubble.append(_team_row(club, seed=None,
                                               status=f"{gap:g} GB of the last Wild Card",
                                               gap=f"{gap:g} GB"))

        # Status for the "games that matter" ranking: a club is in the field if it leads
        # a division or holds a Wild Card, and its gap is its distance from whichever
        # race it is closest in.
        for club in teams:
            in_field = club in leaders or club in others[:3]
            if in_field:
                gap = 0.0
            else:
                div_gap = _gb(club, next(c for c in leaders if c.division == club.division))
                wc_gap = _gb(club, cutoff) if cutoff else 99.0
                gap = max(0.0, min(div_gap, wc_gap))
            status_by_id[club.team_id] = {
                "conference": conference, "division": club.division,
                "gap": gap, "status": "In the field" if in_field else f"{gap:g} GB",
                "in_field": in_field}

        panels.append({"name": f"{short} Wild Card", "field": wc_field, "bubble": wc_bubble,
                       "decided": False, "note": "", "divisions": division_panels,
                       "division_title": f"{short} division races"})
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


def implication(away: dict | None, home: dict | None,
                away_name: str | None = None,
                home_name: str | None = None) -> tuple[float, str]:
    """How much a game moves a playoff race, and why, from both sides' race status.

    Shared by the playoff page's "games that matter" list and the slate card's chip, so
    the two can never disagree about which games count. Returns ``(0.0, "")`` when the
    game touches nobody in the race.
    """
    if not away and not home:
        return 0.0, ""
    score = 0.0
    for side in (away, home):
        if side:
            score += 7 if side["in_field"] else max(0.0, 7 - side["gap"])
    same_conf = bool(away and home and away["conference"] == home["conference"])
    same_div = bool(same_conf and away["division"] == home["division"])
    if same_conf:
        score += 3
    if same_div:
        score += 4
    if score < 7:
        return 0.0, ""
    if same_div:
        division = (away["division"] or "").replace("American League", "AL") \
                                           .replace("National League", "NL")
        return score, f"Direct {division} race."
    if same_conf:
        return score, (f"Both clubs are part of the "
                       f"{_short_conference(away['conference'])} playoff picture.")
    side = away or home
    club = away_name if away else home_name
    return score, f"{club} is {side['status'].lower()}."


def _important_games(games: list[dict], status: dict[str, dict]) -> list[dict]:
    ranked = []
    for game in games:
        if game.get("phase") != "regular" or game.get("state") == "final":
            continue
        away, home = status.get(str(game.get("away_id"))), status.get(str(game.get("home_id")))
        score, why = implication(away, home, game.get("away_short"), game.get("home_short"))
        if not why:
            continue
        try:
            start = datetime.fromisoformat(str(game.get("game_date")).replace("Z", "+00:00"))
            day = start.strftime("%a, %b %-d")
            start_date = start.date().isoformat()
        except (TypeError, ValueError):
            day = str(game.get("game_date") or "")[:10]
            start_date = day
        ranked.append((score, str(game.get("game_date") or ""), {
            # `day` is for reading; `date` is for deciding whether a matchup page for it
            # exists, which only the web layer can answer — it owns the slate day slugs.
            "game_id": game.get("game_pk"), "day": day, "date": start_date,
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
                "has_data": False, "window": window, "show_rivals": True,
                "format_note": "Three division leaders + three Wild Cards",
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
            "show_rivals": True,
            "format_note": "Three division leaders + three Wild Cards",
            "games": _important_games(in_window or schedule, status),
            "schedule_available": schedule_available,
            "window_end": end, "as_of": today, "has_data": bool(table)}


# The card's bar, which is deliberately far above the list's floor of 7. The race page
# admits anything over 7 and then *ranks and truncates to eight*, so its effective cut is
# much higher than its floor — at 7 the chip landed on seven of nine cards, and a mark
# that appears on almost everything marks nothing. Measured against two real slates, 15
# keeps the four or five games that are genuinely about the race and drops the ones that
# merely involve someone in it.
CARD_IMPLICATION_SCORE = 15.0


def slate_implications(games, as_of: date | None = None, db_path: Path = DB_PATH,
                       min_score: float = CARD_IMPLICATION_SCORE) -> dict[str, str]:
    """``{game_id: why}`` for slate games that genuinely move a playoff race.

    Scored by the same function as the race page's "games that matter", so a game cannot
    be consequential on one surface and ordinary on the other — only the bar differs,
    because the page ranks and this does not.

    Silent outside the race window: in April every game is equally not about the
    playoffs, and a chip saying otherwise would be noise on every card.
    """
    table = standings.for_league("MLB", as_of, db_path=db_path)
    if playoff_window.state("MLB", table) != "live":
        return {}
    _panels, status = _race_rows(table)
    out: dict[str, str] = {}
    for game in games:
        if getattr(game, "league", None) != "MLB" or game.state == "final":
            continue
        away = status.get(str(game.away_id))
        home = status.get(str(game.home_id))
        score, why = implication(away, home, game.away_short, game.home_short)
        if why and score >= min_score:
            out[str(game.game_id)] = why
    return out
