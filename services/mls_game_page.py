"""Builder for the MLS matchup page.

Assembles an immutable :class:`MLSGamePage`. When collected MLS team data exists
strictly before the match date, the Snapshot, Tactical proxies, Attacking
Profile, Discipline, and Storylines are built from **real, leakage-safe**
aggregates (``services/mls_repository`` + ``services/mls_analytics``). When no
team data is available yet, every section degrades to the honest Phase-3A state
(``UNAVAILABLE``/``PROJECTED``) — no invented statistics, no fabricated tactical
conclusions.

Players-to-Watch and Projected Lineups remain intentionally unavailable this
phase (Option A collects team stats only). The layout never changes; only the
section data states do — the blueprint's progressive-intelligence ladder.
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
from services import mls_analytics as A
from services import mls_repository as R

ENGINE_VERSION = "mls-game-page-v2"

_NA = "—"


# ------------------------------------------------------- number formatting ---
def _n1(x) -> str:
    return f"{x:.1f}" if x is not None else _NA


def _n2(x) -> str:
    return f"{x:.2f}" if x is not None else _NA


def _pct0(x) -> str:
    return f"{x:.0f}%" if x is not None else _NA


def _signed1(x) -> str:
    return f"{x:+.1f}" if x is not None else _NA


def _ordinal(n) -> str:
    if n is None:
        return _NA
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _better(home, away, threshold: float, lower_better: bool = False) -> str | None:
    if home is None or away is None:
        return None
    if abs(home - away) < threshold:
        return "even"
    if lower_better:
        return "home" if home < away else "away"
    return "home" if home > away else "away"


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


def _team_line(name, short, logo, color, record, form, standing=None) -> MLSTeamLine:
    pts = _points(record)
    return MLSTeamLine(
        name=name or short or "TBD",
        short=short or name or "TBD",
        logo=logo,
        color=color,
        record=record,
        form=_form_tuple(form),
        points_display=f"{pts} pts" if pts is not None else None,
        standing=standing,
    )


def _standing_line(standing: dict | None) -> str | None:
    """Compact hero standing, e.g. '6th in West · 24 pts'."""
    if not standing or standing.get("conference_rank") is None:
        return None
    conf = (standing.get("conference") or "").replace(" Conference", "")
    rank = _ordinal(standing["conference_rank"])
    pts = standing.get("points")
    tail = f" · {int(pts)} pts" if pts is not None else ""
    return f"{rank} in {conf}{tail}" if conf else f"{rank}{tail}"


# --------------------------------------------------------------- HERO --------
def _build_hero(game: SlateGame, away_standing: dict | None = None,
                home_standing: dict | None = None) -> MLSHero:
    m = game.meta or {}
    away = _team_line(game.away_name, game.away_display, game.away_logo,
                      m.get("away_color"), m.get("away_record"), m.get("away_form"),
                      _standing_line(away_standing))
    home = _team_line(game.home_name, game.home_display, game.home_logo,
                      m.get("home_color"), m.get("home_record"), m.get("home_form"),
                      _standing_line(home_standing))
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
        note=("Players are chosen for their role in *this* matchup, not fame. "
              "Position-aware player evaluation requires richer player data than the "
              "current feed provides (it lacks minutes, passing, and defensive "
              "actions per player), so this section stays honest until that is sourced."),
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


# ======================================================================
# REAL-DATA SECTION BUILDERS (Phase 3B). Used when collected team data
# exists strictly before the match date; otherwise the fallbacks above run.
# ======================================================================
def _build_snapshot_real(hero, ha, aa, ha_ppm=None, aa_ppm=None) -> MLSSnapshot:
    """Snapshot = *outcomes* ("who's been stronger"). Distinct from Tactical
    (style contrasts), Attacking (volume), and Discipline. ``ha_ppm``/``aa_ppm``
    are the home club's home-form and away club's away-form points per match."""
    def row(label, hv, av, thr, lower=False, fmt=_n1):
        return MLSSnapshotRow(label, fmt(av), fmt(hv),
                              _better(hv, av, thr, lower), DataState.AVAILABLE)
    rows = [
        row("Goals / match", ha.get("goals_for"), aa.get("goals_for"), 0.15),
        row("Goals allowed / match", ha.get("goals_against"), aa.get("goals_against"), 0.15, lower=True),
        row("Goal difference / match", ha.get("goal_diff"), aa.get("goal_diff"), 0.2, fmt=_signed1),
        row("Shots / match", ha.get("shots"), aa.get("shots"), 0.8),
        row("Shots on target / match", ha.get("shots_on_target"), aa.get("shots_on_target"), 0.4),
        row("Ball Share", ha.get("possession"), aa.get("possession"), 2.0, fmt=_pct0),
    ]
    if ha_ppm is not None and aa_ppm is not None:
        rows.append(MLSSnapshotRow("Points / match (venue)", _n1(aa_ppm), _n1(ha_ppm),
                                   _better(ha_ppm, aa_ppm, 0.25), DataState.AVAILABLE))
    note = (f"Season to date, strictly before this match — {hero.home.short} "
            f"{ha.get('matches', 0)} matches, {hero.away.short} {aa.get('matches', 0)}. "
            f"“Ball Share” is average possession, not control; “Points / match "
            f"(venue)” is {hero.home.short}'s home form vs {hero.away.short}'s away form.")
    return MLSSnapshot(state=DataState.AVAILABLE, rows=tuple(rows), note=note)


def _build_tactical_real(hero, dims, similar_summary: str) -> MLSTactical:
    """Show only meaningful contrasts. Fewer than two → a compact similar-profile
    interpretation instead of a wall of near-even rows."""
    note = ("Measured box-score contrasts only — never claims about pressing, low "
            "blocks, transitions, width, or line height, which this data can't support.")
    if len(dims) < 2:
        return MLSTactical(state=DataState.AVAILABLE, rows=(), note=note,
                           summary=similar_summary)
    rows = tuple(
        MLSTacticalRow(dimension=d.name, lean=d.edge,
                       away_label=d.away_display, home_label=d.home_display,
                       explanation=d.evidence, state=DataState.AVAILABLE,
                       confidence=d.confidence)
        for d in dims
    )
    return MLSTactical(state=DataState.AVAILABLE, rows=rows, note=note)


def _significant(hv, av, thr: float) -> bool:
    """True when the gap is large enough to be worth a row."""
    return hv is not None and av is not None and abs(hv - av) >= thr


def _build_attacking_real(hero, ha, aa) -> MLSAttacking:
    """Attacking = how volume is generated. Rows below their significance
    threshold are suppressed so near-identical values don't read as noise."""
    dims: list[MLSAttackDimension] = []
    if _significant(ha.get("shot_accuracy"), aa.get("shot_accuracy"), 3.0):
        dims.append(MLSAttackDimension("Shot accuracy", _pct0(aa.get("shot_accuracy")),
            _pct0(ha.get("shot_accuracy")), DataState.AVAILABLE,
            _better(ha.get("shot_accuracy"), aa.get("shot_accuracy"), 3.0)))
    if _significant(ha.get("crosses"), aa.get("crosses"), 2.5):
        dims.append(MLSAttackDimension("Crossing volume / match", _n1(aa.get("crosses")),
            _n1(ha.get("crosses")), DataState.AVAILABLE, None))
    if _significant(ha.get("cross_accuracy"), aa.get("cross_accuracy"), 4.0):
        dims.append(MLSAttackDimension("Cross accuracy", _pct0(aa.get("cross_accuracy")),
            _pct0(ha.get("cross_accuracy")), DataState.AVAILABLE, None))
    # Penalty *attempts per match* (rate, not raw season totals). Penalties are
    # rare, so this row is only shown when the per-match gap clears the threshold;
    # the threshold is not lowered to force a low-signal row to appear.
    if _significant(ha.get("pk_attempts"), aa.get("pk_attempts"), 0.15):
        dims.append(MLSAttackDimension("Penalty attempts / match", _n2(aa.get("pk_attempts")),
            _n2(ha.get("pk_attempts")), DataState.AVAILABLE, None))
    note = ("How each side generates attacking volume — shot accuracy is shots on "
            "target ÷ shots. Near-identical rows are omitted.")
    if not dims:
        return MLSAttacking(state=DataState.AVAILABLE, away_team=hero.away.short,
                            home_team=hero.home.short, dimensions=(), note=note,
                            summary="Similar attacking profiles across the available volume metrics.")
    return MLSAttacking(state=DataState.AVAILABLE, away_team=hero.away.short,
                        home_team=hero.home.short, dimensions=tuple(dims), note=note)


def _build_discipline_real(hero, ha, aa) -> MLSDiscipline:
    """Compact discipline signal. If both clubs sit close to each other, show a
    concise similar-profile line rather than several low-signal rows."""
    rows: list[MLSDisciplineRow] = []
    if _significant(ha.get("fouls"), aa.get("fouls"), 1.0):
        rows.append(MLSDisciplineRow("Fouls / match", _n1(aa.get("fouls")), _n1(ha.get("fouls")),
            DataState.AVAILABLE, _better(ha.get("fouls"), aa.get("fouls"), 1.0, lower_better=True)))
    if _significant(ha.get("yellows"), aa.get("yellows"), 0.4):
        rows.append(MLSDisciplineRow("Yellow cards / match", _n1(aa.get("yellows")), _n1(ha.get("yellows")),
            DataState.AVAILABLE, _better(ha.get("yellows"), aa.get("yellows"), 0.4, lower_better=True)))
    hr, ar = ha.get("reds_total", 0), aa.get("reds_total", 0)
    reds_shown = max(hr, ar) >= 3 or abs(hr - ar) >= 2
    if reds_shown:
        rows.append(MLSDisciplineRow("Red cards (season)", str(ar), str(hr), DataState.AVAILABLE,
            _better(hr, ar, 0.5, lower_better=True)))
    note = "Fouls and cards are a discipline signal, not a measure of pressing. Lower is the edge."
    if reds_shown:
        note += (f" Red cards are season counts, not rates ({hero.home.short} over "
                 f"{ha.get('matches', 0)} matches, {hero.away.short} {aa.get('matches', 0)}).")
    if not rows:
        return MLSDiscipline(state=DataState.AVAILABLE, rows=(), note=note,
                             summary="Both clubs draw fouls and cards at similar, unremarkable rates.")
    return MLSDiscipline(state=DataState.AVAILABLE, rows=tuple(rows), note=note)


def _build_storylines_state(story_objs, home_n: int, away_n: int, hero) -> MLSStorylines:
    """Three honest states: real-with-triggers, real-with-none, partial, or none."""
    real = home_n >= A.MIN_MATCHES_LOW and away_n >= A.MIN_MATCHES_LOW
    if real:
        if story_objs:
            items = tuple(MLSStoryline(title=s.title, detail=s.detail, evidence=s.evidence,
                                       confidence=s.confidence, tone=s.tone) for s in story_objs)
            note = ("Generated deterministically from collected team stats, recent results, "
                    "and the table. Only the strongest, non-redundant storylines are shown.")
            return MLSStorylines(state=DataState.AVAILABLE, items=items, note=note)
        return MLSStorylines(state=DataState.AVAILABLE, items=(),
                             note="No standout storylines. These clubs profile similarly "
                                  "across the available team metrics.")
    if home_n >= 1 or away_n >= 1:
        return MLSStorylines(state=DataState.PARTIAL, items=(),
                             note="Limited match data collected so far — not enough of a "
                                  "sample to surface reliable storylines yet.")
    # No collected team data at all — fall back to record/form storylines if any.
    return _build_storylines(hero)


# ------------------------------------------------------------- HONEST GAPS ----
def _build_honest_gaps(hero: MLSHero, has_team_data: bool = False,
                       n_matches: int | None = None) -> MLSHonestGaps:
    gaps: list[MLSHonestGap] = []
    if not has_team_data:
        gaps.append(MLSHonestGap("Season match stats missing",
            "Goals, shots, possession, and passing are not collected for this match yet, "
            "so the snapshot and profiles are partial."))
    else:
        cover = f" (team stats cover {n_matches} matches each side)" if n_matches else ""
        gaps.append(MLSHonestGap("Team stats, not tracking data",
            f"The snapshot, proxies, and storylines are real team box-score aggregates{cover} — "
            "not positional or event tracking."))
    gaps += [
        MLSHonestGap("Lineups not confirmed",
                     "Projected and confirmed XIs are not connected yet; the pitch shows "
                     "a reference layout, not a prediction."),
        MLSHonestGap("Player-level analysis limited",
                     "The feed lacks per-player minutes, passing, and defensive actions, so "
                     "Players to Watch stays unavailable rather than guessing."),
        MLSHonestGap("No true tactical metrics",
                     "Pressing intensity, defensive-line height, transition speed, and width "
                     "are not measured — the Tactical section shows honest box-score proxies only."),
        MLSHonestGap("No expected goals or tracking",
                     "Expected goals (xG), shot maps, and pressing/heat-map data require an "
                     "advanced provider that is not wired in."),
        MLSHonestGap("No match-event timing",
                     "Goal, card, and substitution timing is collected by the provider but not "
                     "analyzed yet, so the What-to-Watch guide stays general."),
    ]
    return MLSHonestGaps(items=tuple(gaps))


# ----------------------------------------------------------------- BUILD ------
def build_mls_game_page(game: SlateGame, slate_date: date, as_of: date) -> MLSGamePage:
    home_id, away_id = game.home_id, game.away_id
    home_standing = R.standings_lookup(home_id, as_of) if home_id else None
    away_standing = R.standings_lookup(away_id, as_of) if away_id else None
    hero = _build_hero(game, away_standing, home_standing)

    # Leakage-safe team frame strictly before the match date, minus this match.
    frame = R.team_match_frame(as_of, exclude_event_id=game.game_id) if home_id and away_id else None
    ha = R.team_aggregate(frame, home_id) if frame is not None and not frame.empty else {"matches": 0}
    aa = R.team_aggregate(frame, away_id) if frame is not None and not frame.empty else {"matches": 0}
    have_data = ha.get("matches", 0) >= A.MIN_MATCHES_LOW and aa.get("matches", 0) >= A.MIN_MATCHES_LOW

    if have_data:
        # Venue splits + recent form + league context (all leakage-safe).
        ha_home = R.team_aggregate(frame, home_id, venue="home")
        aa_away = R.team_aggregate(frame, away_id, venue="away")
        h_last5 = R.recent_results(frame, home_id, n=5)
        a_last5 = R.recent_results(frame, away_id, n=5)
        league = R.league_averages(frame)

        dims = A.proxy_dimensions(ha, aa, home_name=hero.home.short, away_name=hero.away.short)
        traits = A.shared_traits(ha, aa, league)
        # Similar-profile message is scoped to *style* (the tactical proxies), so it
        # never contradicts a lopsided Snapshot. A lone surviving edge is surfaced.
        if len(dims) == 1:
            similar = f"Mostly even on style — the one clear edge is {dims[0].name.lower()}: {dims[0].evidence}"
        else:
            similar = ("Few clear style edges. These clubs are similar in passing completion, "
                       "defensive shot pressure, and corner volume, even when their overall "
                       "results differ.")
            if traits:
                similar = f"{similar} Both also {traits[0]}."
        story_objs = A.storylines(
            hero.home.short, hero.away.short, home_agg=ha, away_agg=aa,
            home_last5=h_last5, away_last5=a_last5, league=league,
            home_standing=home_standing, away_standing=away_standing,
            home_home_ppm=ha_home.get("ppm"), away_away_ppm=aa_away.get("ppm"))

        snapshot = _build_snapshot_real(hero, ha, aa, ha_home.get("ppm"), aa_away.get("ppm"))
        tactical = _build_tactical_real(hero, dims, similar)
        storylines = _build_storylines_state(story_objs, ha["matches"], aa["matches"], hero)
        attacking = _build_attacking_real(hero, ha, aa)
        discipline = _build_discipline_real(hero, ha, aa)
        honest = _build_honest_gaps(hero, has_team_data=True, n_matches=min(ha["matches"], aa["matches"]))
        detail = (f"Team match stats from ESPN MLS, strictly before {as_of.isoformat()} "
                  f"({hero.home.short} {ha['matches']} matches, {hero.away.short} {aa['matches']}). "
                  f"Standings snapshot included. No player, event, or tracking data yet.")
    else:
        snapshot = _build_snapshot(hero)
        tactical = _build_tactical()
        storylines = _build_storylines_state(None, ha.get("matches", 0), aa.get("matches", 0), hero)
        attacking = _build_attacking(hero)
        discipline = _build_discipline()
        honest = _build_honest_gaps(hero, has_team_data=False)
        detail = ("Live from the ESPN MLS feed: teams, records, recent form, colors, and "
                  f"kickoff. Team match stats not yet collected for these clubs. As of {as_of.isoformat()}.")

    data_status = DataStatus(source="ESPN MLS", status=SourceStatus.LIVE, detail=detail)

    return MLSGamePage(
        hero=hero,
        snapshot=snapshot,
        tactical=tactical,
        storylines=storylines,
        lineups=_build_lineups(hero),
        players=_build_players(),
        attacking=attacking,
        discipline=discipline,
        timeline=_build_timeline(),
        honest_gaps=honest,
        data_status=data_status,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        as_of=as_of.isoformat(),
    )
