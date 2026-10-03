"""The MLS playoff race: two conference tables, scored on points, cut at seventh and ninth.

**The format, from the source.** Nine clubs per conference reach the MLS Cup Playoffs:
places 1-7 go straight to Round One (a best-of-three series) and places 8-9 play the Wild
Card matches. That is ESPN's own standings note on each club ("Qualifies for MLS Cup
Playoffs - Round One Best-of-3 series" / "- Wild Card Matches"), read on 2026-10-02, not a
format remembered from another season.

**Why its own builder.** MLS is scored, not won: three points a win, one a draw, ordered by
points with official tiebreakers. "Games back" means nothing where a draw is a result, so
the gap is in points, and the reach is points plus three for every game left. The order
is the stored ``conference_rank`` — ESPN's, tiebreakers applied — never re-derived here.

**Clinched and out are arithmetic, not forecasts, and deliberately conservative.** A club
has clinched a place when at most (places - 1) other clubs could still reach its points
total; it is out when at least that many clubs already have more points than it can reach.
A tie is counted against the club both ways, because MLS breaks ties on wins and goal
difference that points alone cannot settle — so "clinched" may arrive a match later than
the league announces it, and never earlier.
"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from src.config import DB_PATH

SEASON_GAMES = 34
ROUND_ONE = 7          # places that go straight to Round One
FIELD = 9              # places that reach the playoffs (8-9: Wild Card matches)
NEAR_LINE = 6          # points from ninth that make a meeting a "six-pointer"
WINDOW_DAYS = 14


@dataclass(frozen=True)
class Club:
    team_id: str
    name: str
    abbr: str | None
    logo: str | None
    conference: str
    rank: int
    points: int
    played: int
    wins: int
    draws: int
    losses: int
    goal_difference: int

    @property
    def left(self) -> int:
        return max(0, SEASON_GAMES - self.played)

    @property
    def reach(self) -> int:
        """The most points the club can still finish on."""
        return self.points + 3 * self.left

    @property
    def record(self) -> str:
        return f"{self.wins}-{self.draws}-{self.losses}"

    @property
    def gd(self) -> str:
        return f"+{self.goal_difference}" if self.goal_difference > 0 else str(self.goal_difference)


def load_table(as_of: date | None = None, db_path: Path = DB_PATH) -> list[Club]:
    """The newest stored MLS table on or before ``as_of``, with names, in official order."""
    day = (as_of or date.today()).isoformat()
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            snap = conn.execute("SELECT MAX(snapshot_date) FROM mls_standings "
                                "WHERE snapshot_date <= ?", (day,)).fetchone()[0]
            if not snap:
                return []
            names = {str(r["team_id"]): r for r in conn.execute(
                "SELECT team_id, name, abbr, logo FROM mls_teams")}
            rows = conn.execute("SELECT * FROM mls_standings WHERE snapshot_date = ? "
                                "ORDER BY conference, conference_rank", (snap,)).fetchall()
    except sqlite3.OperationalError:
        return []
    clubs = []
    for r in rows:
        meta = names.get(str(r["team_id"]))
        clubs.append(Club(
            team_id=str(r["team_id"]), name=meta["name"] if meta else f"Team {r['team_id']}",
            abbr=meta["abbr"] if meta else None, logo=meta["logo"] if meta else None,
            conference=r["conference"] or "MLS", rank=int(r["conference_rank"] or 99),
            points=int(r["points"] or 0), played=int(r["games_played"] or 0),
            wins=int(r["wins"] or 0), draws=int(r["draws"] or 0), losses=int(r["losses"] or 0),
            goal_difference=int(r["goal_difference"] or 0)))
    return clubs


def window_state(clubs: list[Club]) -> str:
    """The same four states as ``playoff_window``, from games played rather than W-L."""
    from services import playoff_window

    season, threshold = playoff_window.LEAGUE_WINDOWS["MLS"]
    if not clubs or not any(c.played for c in clubs):
        return "preseason"
    left = [max(0, season - c.played) for c in clubs]
    if max(left) == 0:
        return "final"
    return "live" if min(left) <= threshold else "early"


def clinched(club: Club, conference: list[Club], places: int) -> bool:
    """At most ``places - 1`` other clubs can still reach this club's points (ties count
    against it)."""
    rivals = sum(1 for c in conference if c is not club and c.reach >= club.points)
    return rivals <= places - 1


def eliminated(club: Club, conference: list[Club], places: int) -> bool:
    """At least ``places`` other clubs already have more points than this club can reach."""
    ahead = sum(1 for c in conference if c is not club and c.points > club.reach)
    return ahead >= places


def _short(conference: str) -> str:
    return conference.replace(" Conference", "")


def _row(club: Club, *, seed: int | None, status: str, gap: str) -> dict:
    return {"id": club.team_id, "seed": seed, "name": club.name, "logo": club.logo,
            "record": f"{club.points} pts", "status": status, "gap": gap,
            "remaining": club.left, "streak": ""}


def race(clubs: list[Club]) -> tuple[list[dict], dict[str, dict]]:
    """One panel per conference: Round One places, Wild Card places, then the clubs that
    can still reach ninth. Plus a per-club status map for the games list."""
    conferences: dict[str, list[Club]] = {}
    for c in clubs:
        conferences.setdefault(c.conference, []).append(c)

    panels, status = [], {}
    for name, members in sorted(conferences.items()):
        members.sort(key=lambda c: c.rank)
        ninth = members[FIELD - 1] if len(members) >= FIELD else None
        tenth = members[FIELD] if len(members) > FIELD else None

        def place_status(club: Club) -> str:
            # Only the clinch is worth words: which places a row holds, the table's own
            # sections already say, and repeating it pushed the record out of view.
            if clinched(club, members, ROUND_ONE):
                return "Clinched Round One · "
            if clinched(club, members, FIELD):
                return "Clinched a playoff place · "
            return ""

        field, wildcard, chasing, out = [], [], [], []
        for seed, club in enumerate(members, 1):
            line = f"{club.record} · GD {club.gd}"
            # The cushion over tenth — the first club outside — is the number a club in
            # the places is defending; it reads "+0" when tenth is level and only the
            # tiebreakers separate them.
            cushion = ""
            if tenth is not None:
                diff = club.points - tenth.points
                cushion = "level with 10th on points · " if diff == 0 else f"+{diff} on 10th · "
            if seed <= FIELD:
                row = _row(club, seed=seed, status=f"{place_status(club)}{cushion}{line}", gap="")
                (field if seed <= ROUND_ONE else wildcard).append(row)
            elif ninth is not None and not eliminated(club, members, FIELD):
                behind = ninth.points - club.points
                where = "level with 9th on points" if behind == 0 else f"{behind} pts behind 9th"
                chasing.append(_row(club, seed=None,
                                    status=f"{where} · can reach {club.reach} · {line}",
                                    gap=f"−{behind}"))
            else:
                out.append(club)
            gap_pts = 0 if seed <= FIELD else (ninth.points - club.points if ninth else 99)
            status[club.team_id] = {
                "conference": name, "in_field": seed <= FIELD, "gap": gap_pts, "rank": seed,
                "near_line": ninth is not None and abs(club.points - ninth.points) <= NEAR_LINE,
                "out": club in out}

        note = ""
        if not chasing and out:
            note = (f"Every club below ninth is mathematically out: none can reach "
                    f"{ninth.points} points." if ninth else "")
        elif not chasing:
            note = "Nobody below ninth is close."
        panels.append({
            "name": f"{_short(name)} race", "field": field, "wildcard": wildcard,
            "bubble": chasing, "decided": bool(note), "note": note,
            "out": [c.name for c in out], "divisions": [], "division_title": ""})
    return panels, status


def fetch_fixtures(start: date, end: date) -> list[dict]:
    """Regular-season MLS fixtures between two dates, one ESPN request per day.

    ESPN's soccer scoreboard ignores a date range (it returns nothing), so the days are
    fetched in parallel — about two dozen small requests for a fortnight."""
    from src import espn_soccer

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        batches = list(pool.map(lambda d: espn_soccer.schedule("usa.1", d), days))
    return [g for batch in batches for g in batch
            if (g.get("season_slug") or "regular-season") == "regular-season"]


def _important(fixtures: list[dict], status: dict[str, dict]) -> list[dict]:
    ranked = []
    for g in fixtures:
        if g.get("state") == "final" or g.get("completed"):
            continue
        a, h = status.get(str(g.get("away_id"))), status.get(str(g.get("home_id")))
        if not a and not h:
            continue
        live = [s for s in (a, h) if s and not s["out"]]
        if not live:
            continue
        score = sum(7 if s["in_field"] else max(0, 7 - s["gap"]) for s in live)
        same = bool(a and h and a["conference"] == h["conference"])
        if same:
            score += 3
        if same and a["near_line"] and h["near_line"]:
            score += 6
            why = (f"A six-pointer at the line: both clubs are within {NEAR_LINE} points of "
                   f"ninth in the {a['conference']}.")
        elif same:
            why = f"Both clubs are in the {a['conference']} race."
        else:
            side, club = (a, g.get("away_short")) if a and not a["out"] else (h, g.get("home_short"))
            why = (f"{club} {'holds a playoff place' if side['in_field'] else 'is chasing ninth'}.")
        if score < 12:
            continue
        try:
            start = datetime.fromisoformat(str(g.get("game_date")).replace("Z", "+00:00"))
            day, start_date = start.strftime("%a, %b %-d"), start.date().isoformat()
        except (TypeError, ValueError):
            day = start_date = str(g.get("game_date") or "")[:10]
        ranked.append((score, str(g.get("game_date") or ""), {
            "game_id": g.get("game_id"), "day": day, "date": start_date,
            "away": g.get("away_short") or g.get("away"), "home": g.get("home_short") or g.get("home"),
            "away_logo": g.get("away_logo"), "home_logo": g.get("home_logo"), "why": why}))
    ranked.sort(key=lambda r: (-r[0], r[1]))
    return [r[2] for r in ranked[:8]]


def build_context(as_of: date | None = None, db_path: Path = DB_PATH,
                  fixture_fetcher: Callable | None = None) -> dict:
    from services import playoff_window

    # Looked up at call time, not bound as a default: a default binds at import, so a
    # test patching ``fetch_fixtures`` would silently still hit ESPN.
    fixture_fetcher = fixture_fetcher or fetch_fixtures

    today = as_of or date.today()
    clubs = load_table(today, db_path)
    window = window_state(clubs)
    eyebrow, disclaimer = playoff_window.headline("MLS", window)
    base = {"section": "playoffs", "league": "MLS", "window": window, "eyebrow": eyebrow,
            "disclaimer": disclaimer.replace("Ties and official postseason tiebreakers are "
                                             "not projected.",
                                             "Order uses the league's tiebreakers; clinched "
                                             "and out count ties against the club."),
            "show_rivals": False, "record_label": "Points", "gap_label": "Gap",
            "format_note": "Places 1-7 go to Round One; 8-9 play the Wild Card matches",
            "page_read": "Each conference's playoff places, the clubs still able to reach "
                         "ninth, and the matches that can move those lines. Scored on points: "
                         "three for a win, one for a draw.",
            "games_note": "Highest-leverage matches in the next two weeks, from the current "
                          "conference tables.",
            "as_of": today, "standings_league": "MLS"}
    if window in ("early", "preseason"):
        return {**base, "panels": [], "games": [], "schedule_available": True,
                "window_end": None, "has_data": False}

    panels, status = race(clubs)
    end = today + timedelta(days=WINDOW_DAYS)
    fixtures, available = [], True
    if window == "live":
        try:
            fixtures = fixture_fetcher(today, end)
        except Exception:                                # noqa: BLE001
            available = False
    return {**base, "panels": panels, "games": _important(fixtures, status),
            "schedule_available": available, "window_end": end if window == "live" else None,
            "has_data": bool(panels)}
