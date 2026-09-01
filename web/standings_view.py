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

from datetime import date, timedelta

from services import standings

# The order leagues appear, and what each calls its groups. A league only shows up once
# it has rows, so an offseason league is absent rather than empty.
LEAGUE_ORDER = ("MLB", "NFL", "NBA", "NHL")
GROUP_NOUN = {"MLB": "Division", "NFL": "Division", "NBA": "Division", "NHL": "Division"}

# How far back to look for a game before calling a league out of season. Wide enough
# to survive an All-Star break or a scheduling gap, short enough that a finished
# season stops showing within a fortnight.
_IN_SEASON_DAYS = 14


def available_leagues(as_of: date | None = None, db_path=None) -> list[str]:
    """Leagues with standings worth showing.

    "Has rows" is not the test — before its opener every team is 0-0, and a table of
    thirty-two zeroes tells a reader nothing while looking authoritative. A league
    appears once someone has played, which is the same rule the slate applies when it
    refuses to rank an opening night on nothing.
    """
    kwargs = {"db_path": db_path} if db_path else {}
    playing = _in_season(as_of, db_path)
    out = []
    for league in LEAGUE_ORDER:
        table = standings.for_league(league, as_of, **kwargs)
        if not table or league not in playing:
            continue
        if any((t.wins + t.losses + t.ties) > 0 for t in table.values()):
            out.append(league)
    return out


def _in_season(as_of: date | None, db_path=None) -> set[str]:
    """Leagues that have actually had games on a recent slate.

    "Someone has played" is not enough on its own. ESPN keys a season by its *start*
    year, so asking for 2026 in September returns the NBA's completed 2025-26 table —
    a full 82-game season, every record final, presented as though it were current. The
    schedule already knows which leagues are playing; this asks it rather than trying
    to infer a season calendar per sport.
    """
    import sqlite3

    from src.config import DB_PATH

    end = as_of or date.today()
    start = (end - timedelta(days=_IN_SEASON_DAYS)).isoformat()
    try:
        with sqlite3.connect(db_path or DB_PATH) as conn:
            rows = conn.execute(
                "SELECT DISTINCT league FROM schedule_cache "
                "WHERE game_count > 0 AND slate_date BETWEEN ? AND ?",
                (start, end.isoformat())).fetchall()
    except sqlite3.OperationalError:
        return set(LEAGUE_ORDER)      # no cache to consult: do not hide everything
    return {r[0] for r in rows}


def build_context(league: str | None, as_of: date | None = None, db_path=None) -> dict:
    # db_path is threaded rather than read from the module default so this is testable:
    # `db_path=DB_PATH` binds at import, so patching the constant afterwards changes
    # nothing and a test would silently read the real database.
    kwargs = {"db_path": db_path} if db_path else {}
    leagues = available_leagues(as_of, db_path)
    chosen = league if league in leagues else (leagues[0] if leagues else None)
    if chosen is None:
        return {"section": "standings", "leagues": [], "league": None, "groups": []}

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
        "group_noun": GROUP_NOUN.get(chosen, "Division"),
        "groups": groups,
    }
