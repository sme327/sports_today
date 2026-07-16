"""Builder for the MLS matchup page.

Assembles an immutable :class:`MLSGamePage` from the (real) live schedule. The
hero and a recent-form/record snapshot are genuine provider data; a small
deterministic storyline engine reads only the real record + form. Every section
that needs a soccer-stats pipeline that does not exist yet is emitted in an
honest :class:`DataState` (``UNAVAILABLE``/``PROJECTED``) with its real component
shell — no invented statistics, no fabricated tactical conclusions.

This is "Version 1: rule-based" in the blueprint's progressive-intelligence
ladder. The layout is fixed; later versions swap section states for richer data
without touching the view.
"""

from __future__ import annotations

from datetime import date, datetime

from components.format import format_game_time
from domain.mls_game_page import (
    DataState, MLSArchetype, MLSAttacking, MLSAttackDimension, MLSDiscipline,
    MLSDisciplineRow, MLSGamePage, MLSHero, MLSHonestGap, MLSHonestGaps,
    MLSLineup, MLSLineups, MLSPitchSlot, MLSPlayersToWatch, MLSSnapshot,
    MLSSnapshotRow, MLSStoryline, MLSStorylines, MLSTactical, MLSTacticalRow,
    MLSTeamLine, MLSTimeline, MLSTimelinePhase,
)
from domain.models import DataStatus, SlateGame, SourceStatus

ENGINE_VERSION = "mls-game-page-v1"

_NA = "—"


# ------------------------------------------------------------- HELPERS -------
def _form_tuple(value) -> tuple[str, ...]:
    """Accept a tuple/list/string of results (survives JSON cache round-trip)."""
    if not value:
        return ()
    if isinstance(value, str):
        return tuple(ch for ch in value.upper() if ch in ("W", "D", "L"))
    return tuple(str(ch).upper() for ch in value if str(ch).upper() in ("W", "D", "L"))


def _parse_record(record: str | None) -> tuple[int, int, int] | None:
    """MLS records are 'W-D-L'. Returns (w, d, l) or None if unparseable."""
    if not record:
        return None
    parts = str(record).split("-")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _points(record: str | None) -> int | None:
    parsed = _parse_record(record)
    if not parsed:
        return None
    w, d, _ = parsed
    return w * 3 + d


def _win_pct(record: str | None) -> float | None:
    parsed = _parse_record(record)
    if not parsed:
        return None
    w, d, l = parsed
    total = w + d + l
    return (w / total) if total else None


def _team_line(name, short, logo, color, record, form) -> MLSTeamLine:
    pts = _points(record)
    return MLSTeamLine(
        name=name or short or "TBD",
        short=short or name or "TBD",
        logo=logo,
        color=color,
        record=record,
        form=_form_tuple(form),
        points_display=f"{pts} pts" if pts is not None else None,
    )


# --------------------------------------------------------------- HERO --------
def _build_hero(game: SlateGame) -> MLSHero:
    m = game.meta or {}
    away = _team_line(game.away_name, game.away_display, game.away_logo,
                      m.get("away_color"), m.get("away_record"), m.get("away_form"))
    home = _team_line(game.home_name, game.home_display, game.home_logo,
                      m.get("home_color"), m.get("home_record"), m.get("home_form"))
    return MLSHero(
        competition=m.get("competition") or "Major League Soccer",
        kickoff=format_game_time(game.start_time),
        venue=game.venue,
        broadcast=m.get("broadcast") or None,
        away=away,
        home=home,
        state=game.state,
        away_score=game.away_score,
        home_score=game.home_score,
        status_detail=game.status_detail,
    )


# ------------------------------------------------------- MATCHUP SNAPSHOT -----
def _form_summary(form: tuple[str, ...]) -> str:
    if not form:
        return _NA
    w = form.count("W")
    d = form.count("D")
    l = form.count("L")
    return f"{w}W-{d}D-{l}L"


def _build_snapshot(hero: MLSHero) -> MLSSnapshot:
    a, h = hero.away, hero.home
    rows: list[MLSSnapshotRow] = []

    # Real rows (from the live schedule).
    def _better_num(av, hv):
        if av is None or hv is None:
            return None
        return "away" if av > hv else "home" if hv > av else "even"

    a_pts, h_pts = _points(a.record), _points(h.record)
    rows.append(MLSSnapshotRow("Record", a.record or _NA, h.record or _NA,
                               None, DataState.AVAILABLE))
    rows.append(MLSSnapshotRow("Points", a.points_display or _NA, h.points_display or _NA,
                               _better_num(a_pts, h_pts), DataState.AVAILABLE))
    rows.append(MLSSnapshotRow("Last 5", _form_summary(a.form), _form_summary(h.form),
                               _better_num(a.form.count("W"), h.form.count("W")),
                               DataState.AVAILABLE))

    # Rows that need a collected match-stats pipeline (honest placeholders).
    for label in ("Goals / match", "Goals allowed", "Possession", "Shots on target",
                  "Passing accuracy"):
        rows.append(MLSSnapshotRow(label, _NA, _NA, None, DataState.UNAVAILABLE))

    return MLSSnapshot(
        state=DataState.PARTIAL,
        rows=tuple(rows),
        note=("Record, points, and recent results are live from the league feed. "
              "Season attacking and defensive rates arrive with match-stats collection."),
    )


# ------------------------------------------------------- TACTICAL MATCHUP -----
_TACTICAL_DIMENSIONS = [
    ("Possession", "Who wants the ball and dictates tempo."),
    ("Pressing", "How high and how aggressively each side wins it back."),
    ("Defensive line", "High line and compress, or drop into a low block."),
    ("Width", "Attack through the channels and wings, or through the middle."),
    ("Transition speed", "Break at pace on turnovers, or rebuild patiently."),
    ("Set-piece danger", "Threat and vulnerability from corners and free kicks."),
    ("Crossing", "How much of the attack arrives via crosses into the box."),
    ("Directness", "Vertical, direct balls forward vs. measured build-up."),
    ("Game control", "Who is more likely to set the rhythm of the match."),
]


def _build_tactical() -> MLSTactical:
    rows = tuple(
        MLSTacticalRow(
            dimension=dim,
            lean=None,
            away_label="—",
            home_label="—",
            explanation=expl,
            state=DataState.UNAVAILABLE,
        )
        for dim, expl in _TACTICAL_DIMENSIONS
    )
    return MLSTactical(
        state=DataState.UNAVAILABLE,
        rows=rows,
        note=("The signature tactical read compares nine dimensions of style. Each "
              "resolves to a home / even / away lean with a one-line reason once "
              "team match data (possession, pressing, shot locations) is collected. "
              "The framework is shown here so the read is stable as data arrives."),
    )


# --------------------------------------------------------- KEY STORYLINES -----
def _build_storylines(hero: MLSHero) -> MLSStorylines:
    """Deterministic storylines from the real record + form only.

    Win/draw/loss counts are order-independent, so no claim depends on the exact
    sequence of recent results (which the feed does not reliably order).
    """
    a, h = hero.away, hero.home
    items: list[MLSStoryline] = []

    # 1) Record contrast — season-long, so higher confidence.
    a_wp, h_wp = _win_pct(a.record), _win_pct(h.record)
    if a_wp is not None and h_wp is not None and abs(a_wp - h_wp) >= 0.28:
        lead, trail = (a, h) if a_wp > h_wp else (h, a)
        items.append(MLSStoryline(
            title=f"{lead.short} the stronger side on paper",
            detail=(f"{lead.short} ({lead.record}) have a markedly better season record "
                    f"than {trail.short} ({trail.record}). Records describe what has "
                    f"happened, not how tonight will be played."),
            evidence=(f"{lead.short}: {lead.record}", f"{trail.short}: {trail.record}"),
            confidence="Moderate",
            tone="neutral",
        ))

    # 2) Recent form — 5-game sample, so lower confidence; counts, not order.
    for team in (a, h):
        wins = team.form.count("W")
        losses = team.form.count("L")
        if team.form and wins >= 3:
            items.append(MLSStoryline(
                title=f"{team.short} arrive in form",
                detail=(f"{team.short} have won {wins} of their last {len(team.form)} "
                        f"across all competitions."),
                evidence=(f"Last {len(team.form)}: {_form_summary(team.form)}",),
                confidence="Low",
                tone="up",
            ))
        elif team.form and losses >= 3:
            items.append(MLSStoryline(
                title=f"{team.short} searching for form",
                detail=(f"{team.short} have lost {losses} of their last {len(team.form)}, "
                        f"and will want a response."),
                evidence=(f"Last {len(team.form)}: {_form_summary(team.form)}",),
                confidence="Low",
                tone="down",
            ))

    state = DataState.AVAILABLE if items else DataState.UNAVAILABLE
    note = ("Storylines are generated from real records and recent results. Deeper, "
            "match-specific narratives (home fortress, set-piece edge, finishing "
            "regression) arrive with match-stats collection.")
    return MLSStorylines(state=state, items=tuple(items[:3]), note=note)


# -------------------------------------------------------- PROJECTED LINEUPS ---
def _reference_slots() -> tuple[MLSPitchSlot, ...]:
    """A neutral 4-3-3 template — a layout for reference, not a projection."""
    coords = [
        ("GK", 50, 8),
        ("DF", 16, 28), ("DF", 39, 26), ("DF", 61, 26), ("DF", 84, 28),
        ("MF", 28, 52), ("MF", 50, 50), ("MF", 72, 52),
        ("FW", 22, 80), ("FW", 50, 84), ("FW", 78, 80),
    ]
    return tuple(MLSPitchSlot(role=r, x=x, y=y, name=None) for r, x, y in coords)


def _build_lineups(hero: MLSHero) -> MLSLineups:
    note = "Confirmed XI not yet available — layout shown for reference, not a projection."
    away = MLSLineup(team=hero.away.short, color=hero.away.color, formation=None,
                     slots=_reference_slots(), note=note)
    home = MLSLineup(team=hero.home.short, color=hero.home.color, formation=None,
                     slots=_reference_slots(), note=note)
    return MLSLineups(state=DataState.UNAVAILABLE, away=away, home=home)


# --------------------------------------------------------- PLAYERS TO WATCH ---
_ARCHETYPES = [
    ("Finisher", "The player most likely to convert the chances that fall to them."),
    ("Creator", "The primary source of chances — key passes and final-third vision."),
    ("Ball progressor", "Carries and passes that move play from defense into attack."),
    ("Defensive anchor", "Screens the back line and breaks up the opponent's build-up."),
    ("Goalkeeper", "Shot-stopping and command of the box can swing a tight match."),
]


def _build_players() -> MLSPlayersToWatch:
    archetypes = tuple(MLSArchetype(name=n, description=d, player=None)
                       for n, d in _ARCHETYPES)
    return MLSPlayersToWatch(
        state=DataState.UNAVAILABLE,
        archetypes=archetypes,
        note=("Players are chosen for their role in *this* matchup, not fame. Each "
              "archetype fills in once player match stats and availability are "
              "collected."),
    )


# -------------------------------------------------------- ATTACKING PROFILE ---
_ATTACK_DIMENSIONS = [
    "Patient build-up", "Quick transitions", "Crossing", "Through balls",
    "Set pieces", "Long-range shooting",
]


def _build_attacking(hero: MLSHero) -> MLSAttacking:
    dims = tuple(MLSAttackDimension(label=d, away_value=_NA, home_value=_NA,
                                    state=DataState.UNAVAILABLE)
                 for d in _ATTACK_DIMENSIONS)
    return MLSAttacking(
        state=DataState.UNAVAILABLE,
        away_team=hero.away.short,
        home_team=hero.home.short,
        dimensions=dims,
        note=("How each team creates goals — style, not just totals. Needs shot "
              "locations, assist types, and set-piece data."),
    )


# --------------------------------------------------------------- DISCIPLINE ---
def _build_discipline() -> MLSDiscipline:
    rows = tuple(MLSDisciplineRow(label=l, away_value=_NA, home_value=_NA,
                                  state=DataState.UNAVAILABLE)
                 for l in ("Yellow cards / match", "Red cards", "Fouls / match",
                           "Suspensions"))
    return MLSDiscipline(
        state=DataState.UNAVAILABLE,
        rows=rows,
        note="Cards, fouls, and suspensions arrive with match-stats collection.",
    )


# ----------------------------------------------------- WHAT TO WATCH TIMELINE -
_TIMELINE = [
    ("Pregame", "Set the scene",
     "Note who is at home and how each side's recent results have gone — it often "
     "shapes who takes the initiative early."),
    ("0–15'", "Opening exchanges",
     "Watch which team presses high and which sits off. The first pressing pattern "
     "usually tells you who wants control of the ball."),
    ("Midfield", "The battle for the middle",
     "Central midfield decides whether the game is played through the lines or forced "
     "wide. Whoever wins the second balls tends to set the tempo."),
    ("Tactical shift", "The first adjustment",
     "Around the half hour, look for a full-back pushing on or a striker dropping in — "
     "small changes that unlock or shut down an attack."),
    ("Late match", "Fatigue and gaps",
     "As legs tire, spaces open in transition. Games are often decided by who defends "
     "these moments and who gambles for a winner."),
    ("Substitutions", "Fresh legs, new shape",
     "Substitutions can change the shape entirely — a chaser for a holder, a winger "
     "for a striker. Watch how the balance of the match tilts afterward."),
]


def _build_timeline() -> MLSTimeline:
    phases = tuple(MLSTimelinePhase(marker=m, title=t, guidance=g, kind="generic")
                   for m, t, g in _TIMELINE)
    return MLSTimeline(
        state=DataState.AVAILABLE,
        phases=phases,
        note=("A general match-watching guide. Team-specific tactical cues arrive "
              "with the tactical model."),
    )


# ------------------------------------------------------------- HONEST GAPS ----
def _build_honest_gaps(hero: MLSHero) -> MLSHonestGaps:
    gaps = [
        MLSHonestGap("Lineups not confirmed",
                     "Projected and confirmed XIs are not connected yet; the pitch shows "
                     "a reference layout, not a prediction."),
        MLSHonestGap("Season match stats missing",
                     "Goals, shots, possession, and passing are not collected yet, so the "
                     "snapshot and attacking profiles are partial."),
        MLSHonestGap("Tactical model pending",
                     "The tactical matchup framework is in place but has no team style data "
                     "to resolve its leans."),
        MLSHonestGap("No advanced tracking",
                     "Expected goals (xG), pressing intensity, and heat maps require an "
                     "advanced provider that is not wired in."),
        MLSHonestGap("Small recent-form sample",
                     "Recent-form storylines rest on the last five results — a small, noisy "
                     "sample — so their confidence is low."),
    ]
    return MLSHonestGaps(items=tuple(gaps))


# ----------------------------------------------------------------- BUILD ------
def build_mls_game_page(game: SlateGame, slate_date: date, as_of: date) -> MLSGamePage:
    hero = _build_hero(game)

    real_note = ("Live from the ESPN MLS feed: teams, records, recent form, colors, and "
                 "kickoff. Deeper analysis is honestly marked as it comes online.")
    data_status = DataStatus(
        source="ESPN MLS",
        status=SourceStatus.LIVE,
        detail=(f"{real_note} As of {as_of.isoformat()}."),
    )

    return MLSGamePage(
        hero=hero,
        snapshot=_build_snapshot(hero),
        tactical=_build_tactical(),
        storylines=_build_storylines(hero),
        lineups=_build_lineups(hero),
        players=_build_players(),
        attacking=_build_attacking(hero),
        discipline=_build_discipline(),
        timeline=_build_timeline(),
        honest_gaps=_build_honest_gaps(hero),
        data_status=data_status,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        as_of=as_of.isoformat(),
    )
