"""The WNBA playoff race: one table, top eight, no conferences.

**Why this is not the MLB builder with a different constant.** Baseball's field is six
per league — three division leaders plus three wild cards — so its race is really six
small races and the page is two panels of them. The WNBA has seeded 1-8 across the whole
league since 2016: no divisions, no conference split, no automatic bids. That makes it
simpler, not smaller, and forcing it through "leaders + wild cards per conference" would
invent structure the league does not have.

Same discipline as the MLB page: records, position and the games left to change them.
Description, never a projection — seeds are where clubs sit today, not where they will
finish, and the wording has to keep saying so.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from services import playoff_window, standings
from src.config import DB_PATH

FIELD_SIZE = 8          # the WNBA postseason field
BUBBLE_GAMES = 5        # how far back still counts as chasing


def _row(team, *, seed, status: str, gap: str) -> dict:
    return {"id": team.team_id, "seed": seed, "name": team.team_name, "logo": team.logo,
            "record": team.record, "status": status, "gap": gap,
            "remaining": playoff_window.games_remaining(
                "WNBA", team.wins, team.losses, team.ties),
            "streak": team.streak or ""}


def _games_back(team, cutoff) -> float:
    """Standard games-back against the club holding the last playoff place."""
    return ((cutoff.wins - team.wins) + (team.losses - cutoff.losses)) / 2


def race(table: dict) -> tuple[list[dict], dict[str, dict]]:
    """One panel — the league is one table — plus a per-team status map."""
    if not table:
        return [], {}
    ordered = sorted(table.values(),
                     key=lambda t: (t.win_pct or 0, t.wins), reverse=True)
    field, chasers = ordered[:FIELD_SIZE], ordered[FIELD_SIZE:]
    cutoff = field[-1] if len(field) == FIELD_SIZE else None

    status: dict[str, dict] = {}
    rows = []
    for seed, team in enumerate(field, 1):
        # The top four host a first-round series; saying so is a fact about the format
        # applied to today's order, not a claim that the order holds.
        label = "Top-four seed" if seed <= 4 else "In the field"
        rows.append(_row(team, seed=seed, status=label, gap="In position"))
        status[team.team_id] = {"gap": 0.0, "status": label, "in_field": True}

    bubble = []
    if cutoff is not None:
        for team in chasers:
            gap = max(0.0, _games_back(team, cutoff))
            if gap <= BUBBLE_GAMES:
                label = f"{gap:g} GB of 8th"
                bubble.append(_row(team, seed=None, status=label, gap=f"{gap:g} GB"))
                status[team.team_id] = {"gap": gap, "status": label, "in_field": False}

    # An empty chasing list has two very different meanings — nobody is close, or
    # everybody left is already out — and a page that just shows nothing implies neither.
    # A club needing more games than remain to close the gap cannot get there.
    left = min((playoff_window.games_remaining("WNBA", t.wins, t.losses, t.ties)
                for t in ordered), default=0)
    decided = bool(chasers) and not bubble and all(
        _games_back(t, cutoff) > left for t in chasers) if cutoff else False

    return [{"name": "Playoff field", "field": rows, "bubble": bubble,
             "decided": decided,
             "note": ("The field is set — every club outside it needs more wins than it "
                      "has games left. Only seeding is still in play.") if decided else ""}], status


def build_context(as_of: date | None = None, db_path: Path = DB_PATH) -> dict:
    today = as_of or date.today()
    table = standings.for_league("WNBA", today, db_path=db_path)
    window = playoff_window.state("WNBA", table)
    eyebrow, disclaimer = playoff_window.headline("WNBA", window)

    if window in ("early", "preseason"):
        return {"section": "playoffs", "league": "WNBA", "panels": [], "games": [],
                "schedule_available": True, "window_end": None, "as_of": today,
                "has_data": False, "window": window,
                "eyebrow": eyebrow, "disclaimer": disclaimer,
                "show_rivals": False, "format_note": "Top eight, seeded across the league"}

    panels, _status = race(table)
    return {"section": "playoffs", "league": "WNBA", "panels": panels,
            # No "games that matter" list: the WNBA slate is small and, right now, on a
            # two-week FIBA break. An empty list is honest; an invented one is not.
            "games": [], "schedule_available": True, "window_end": None,
            "as_of": today, "has_data": bool(panels), "window": window,
            "show_rivals": False,
            "format_note": "Top eight, seeded across the league — no conferences",
            "eyebrow": eyebrow, "disclaimer": disclaimer}
