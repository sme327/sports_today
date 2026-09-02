"""Context for the per-league standings pages.

A standings table is the one place this project shows a league whole rather than a
slate. Everywhere else the question is "what should I pay attention to today"; here it
is "where does this team actually sit", which is the reference point the matchup pages
now lean on and the frame the playoff pages will need.

Deliberately plain: records, position, and the splits people actually read (streak, last
ten, home and road). No projections, no playoff odds — those are forecasts, and this page
is description like the rest of the product.
"""

from __future__ import annotations

from datetime import date

from services import playoff_window, standings

# The order leagues appear, and what each calls its groups. A league only shows up once
# it has rows, so an offseason league is absent rather than empty.
LEAGUE_ORDER = ("MLB", "WNBA", "MLS", "NFL", "NBA", "NHL")
GROUP_NOUN = {"MLB": "Division", "NFL": "Division", "NBA": "Division",
              "NHL": "Division", "WNBA": "Conference", "MLS": "Conference"}

# MLS is scored, not won: three points a win, one a draw, and the table is ordered on
# points with goal difference breaking ties. Rendering it in a W-L-GB shape would be a
# category error — "games behind" means nothing in a league where a draw is a result —
# so it carries its own columns and its own source table.
POINTS_LEAGUES = ("MLS",)

# How far back to look for a game before calling a league out of season. Wide enough
# to survive an All-Star break or a scheduling gap, short enough that a finished
# season stops showing within a fortnight.
# Availability is decided by games *remaining*, not by whether a league played recently.
# The old recency rule was written to catch the opposite problem — ESPN keys a season by
# its start year, so asking for 2026 in September returns the NBA's *completed* table —
# and it did that well while failing a case it was never tested against. The WNBA takes
# two weeks off for the FIBA window, and on day fifteen that rule would have called the
# league out of season and dropped its standings days before its playoffs. A break and an
# offseason are indistinguishable through a "recent games" lens; games left tells them
# apart, and the same window already gates the race page.


def available_leagues(as_of: date | None = None, db_path=None) -> list[str]:
    """Leagues with standings worth showing.

    "Has rows" is not the test — before its opener every team is 0-0, and a table of
    thirty-two zeroes tells a reader nothing while looking authoritative. A league
    appears once someone has played, which is the same rule the slate applies when it
    refuses to rank an opening night on nothing.
    """
    kwargs = {"db_path": db_path} if db_path else {}
    out = []
    for league in LEAGUE_ORDER:
        if league in POINTS_LEAGUES:
            if _mls_context(as_of, db_path):
                out.append(league)
            continue
        table = standings.for_league(league, as_of, **kwargs)
        if playoff_window.state(league, table) in ("early", "live"):
            out.append(league)
    return out


def _mls_context(as_of: date | None, db_path=None) -> list[dict]:
    """MLS from its own table, joined to the names ESPN supplies for the same ids."""
    import sqlite3

    from src.config import DB_PATH

    try:
        with sqlite3.connect(db_path or DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            latest = conn.execute(
                "SELECT MAX(snapshot_date) FROM mls_standings").fetchone()[0]
            if not latest:
                return []
            names = {r[0]: (r[1], r[2]) for r in conn.execute(
                "SELECT team_id, name, logo FROM mls_teams")}
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM mls_standings WHERE snapshot_date = ? "
                "ORDER BY conference, conference_rank", (latest,))]
    except sqlite3.OperationalError:
        return []

    grouped: dict[str, list] = {}
    for row in rows:
        name, logo = names.get(str(row["team_id"]), (None, None))
        grouped.setdefault(row["conference"] or "Table", []).append({
            "rank": row["conference_rank"],
            "name": name or f"Team {row['team_id']}",
            "logo": logo,
            "points": row["points"],
            "played": row["games_played"],
            "record": f"{row['wins']}-{row['draws']}-{row['losses']}",
            "goal_difference": (f"+{row['goal_difference']}"
                                if (row["goal_difference"] or 0) > 0
                                else str(row["goal_difference"] or 0)),
            "leader": row["conference_rank"] == 1,
        })
    return [{"name": k, "short": k, "teams": v} for k, v in sorted(grouped.items())]


def build_context(league: str | None, as_of: date | None = None, db_path=None) -> dict:
    # db_path is threaded rather than read from the module default so this is testable:
    # `db_path=DB_PATH` binds at import, so patching the constant afterwards changes
    # nothing and a test would silently read the real database.
    kwargs = {"db_path": db_path} if db_path else {}
    leagues = available_leagues(as_of, db_path)
    chosen = league if league in leagues else (leagues[0] if leagues else None)
    if chosen is None:
        return {"section": "standings", "leagues": [], "league": None, "groups": []}

    if chosen in POINTS_LEAGUES:
        return {"section": "standings", "leagues": leagues, "league": chosen,
                "group_noun": GROUP_NOUN.get(chosen, "Conference"),
                "points_table": True, "groups": _mls_context(as_of, db_path)}

    table = standings.for_league(chosen, as_of, **kwargs)
    grouped: dict[str, list] = {}
    for team in table.values():
        grouped.setdefault(team.division or "Other", []).append(team)

    groups = []
    for name in sorted(grouped):
        teams = sorted(grouped[name], key=lambda t: (t.division_rank or 99, -t.wins))
        groups.append({
            "name": name,
            # The hero uses the short form; the page has room for the full name, and a
            # standings page is exactly where "American League East" is worth spelling.
            "short": teams[0].division_short if teams else name,
            "teams": [{
                "rank": t.division_rank,
                "name": t.team_name,
                "logo": t.logo,
                "record": t.record,
                "win_pct": f"{t.win_pct:.3f}".lstrip("0") if t.win_pct is not None else "",
                # A leader's deficit is zero; printing "0.0" in a GB column reads as a
                # deficit rather than the absence of one. The dash is the convention.
                "games_behind": ("—" if not t.games_behind else f"{t.games_behind:g}"),
                "streak": t.streak or "",
                "last_ten": t.last_ten or "",
                "leader": (t.division_rank == 1),
            } for t in teams],
        })

    return {
        "section": "standings",
        "leagues": leagues,
        "league": chosen,
        "points_table": False,
        "group_noun": GROUP_NOUN.get(chosen, "Division"),
        "groups": groups,
    }
