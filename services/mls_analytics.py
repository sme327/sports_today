"""Deterministic MLS matchup analytics over collected team data (Phase 3B).

Two honest engines, both reading only leakage-safe aggregates from
``services/mls_repository``:

1. ``proxy_dimensions`` — the Tactical Matchup as **measured proxies** (Ball Share,
   Shot Volume, Shot Accuracy, Defensive Shot Pressure, Corner Pressure, Crossing
   Volume, Passing Completion, Card & Foul Rate, Home/Away Performance). It never
   claims to measure pressing, low blocks, transitions, width, directness, or line
   height. It selects the most informative, non-redundant subset.
2. ``storylines`` — rule-based narratives, each with a rule id, inputs, threshold,
   sample size, and confidence. No narrative beyond the underlying metric.

Confidence ladder (no "High" — a dozen unadjusted matches is not high confidence):
``matches ≥ 8 → Moderate``, ``≥ 4 → Low``, else the item is omitted.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_MATCHES_LOW = 4
MIN_MATCHES_MODERATE = 8
EVEN_MAGNITUDE = 0.35   # |home−away| / scale below this → "Even"


def _confidence(n_home: int, n_away: int) -> str | None:
    n = min(n_home, n_away)
    if n >= MIN_MATCHES_MODERATE:
        return "Moderate"
    if n >= MIN_MATCHES_LOW:
        return "Low"
    return None


def _ppm(agg: dict) -> float | None:
    """Points per match from a venue split (3·W + D) / n, via goals result rates.
    Derived from goals_for/against is not enough; we use the recent-results dict
    instead (see storylines). Here agg carries wins/draws when available."""
    return None  # points-per-match is computed from recent_results, not aggregates


# --------------------------------------------------- TACTICAL PROXIES --------
@dataclass(frozen=True)
class ProxyDimension:
    name: str
    home_display: str
    away_display: str
    edge: str            # "home" | "away" | "even"
    evidence: str
    confidence: str
    magnitude: float
    group: str


def _fmt(value: float, unit: str) -> str:
    if unit == "pct":
        return f"{value:.0f}%"
    if unit == "one":
        return f"{value:.1f}"
    return f"{value:.1f}"


# Tactical owns exactly these proxies (each other metric lives in one other
# section: Ball Share/shots → Snapshot, shot accuracy/crossing → Attacking,
# fouls/cards → Discipline, home/away PPM → Snapshot). This removes the cross-
# section duplication found in the Phase-3B review.
_TACTICAL_SPECS = [
    # (name, group, agg_key, scale, lower_better, unit, sentence template)
    ("Passing Completion", "possession", "pass_completion", 6.0, False, "pct",
     "{h} complete {hv} of passes; {a} {av}."),
    ("Defensive Shot Pressure", "defense", "shots_faced", 4.0, True, "one",
     "{h} face {hv} shots per match; {a} face {av} (fewer is better)."),
    ("Corner Pressure", "attack_volume", "corners", 2.5, False, "one",
     "{h} win {hv} corners per match; {a} {av}."),
]


def proxy_dimensions(home_agg: dict, away_agg: dict, *, home_name: str,
                     away_name: str) -> list[ProxyDimension]:
    """The tactical proxies that are a **meaningful, non-redundant** contrast for
    this matchup. Only dimensions with a real edge survive (``magnitude ≥
    EVEN_MAGNITUDE``); near-even rows are suppressed so an even matchup does not
    produce a wall of "Even" rows (the builder shows a similar-profile state)."""
    conf = _confidence(home_agg.get("matches", 0), away_agg.get("matches", 0))
    if conf is None:
        return []
    out: list[ProxyDimension] = []
    for name, group, key, scale, lower, unit, tmpl in _TACTICAL_SPECS:
        hv, av = home_agg.get(key), away_agg.get(key)
        if hv is None or av is None:
            continue
        mag = abs(hv - av) / scale
        if mag < EVEN_MAGNITUDE:
            continue                                   # suppress negligible contrast
        edge = "home" if ((hv < av) == lower) else "away"
        out.append(ProxyDimension(
            name=name, home_display=_fmt(hv, unit), away_display=_fmt(av, unit),
            edge=edge,
            evidence=tmpl.format(h=home_name, a=away_name, hv=_fmt(hv, unit), av=_fmt(av, unit)),
            confidence=conf, magnitude=round(mag, 3), group=group))
    out.sort(key=lambda d: d.magnitude, reverse=True)
    return out


def shared_traits(home_agg: dict, away_agg: dict, league: dict) -> list[str]:
    """League-relative traits both clubs share (for an even-matchup 'both teams'
    insight). Empty unless a shared value is genuinely unusual vs the league."""
    traits: list[str] = []

    def both(key, margin):
        hv, av, lg = home_agg.get(key), away_agg.get(key), league.get(key)
        if hv is None or av is None or lg is None:
            return 0
        if min(hv, av) - lg >= margin:
            return 1
        if lg - max(hv, av) >= margin:
            return -1
        return 0

    s = both("shots", 2.5)
    if s > 0:
        traits.append("both generate more shots than the MLS average")
    elif s < 0:
        traits.append("both generate fewer shots than average")
    f = both("shots_faced", 2.5)
    if f > 0:
        traits.append("both concede more shots than average")
    return traits


# --------------------------------------------------------- STORYLINES --------
@dataclass(frozen=True)
class Storyline:
    rule_id: str
    title: str
    detail: str
    evidence: tuple[str, ...]
    confidence: str
    tone: str            # "up" | "down" | "neutral"
    strength: float      # for ranking / dedup
    theme: str


def storylines(home_name: str, away_name: str, *, home_agg: dict, away_agg: dict,
               home_last5: dict, away_last5: dict, league: dict,
               home_standing: dict | None, away_standing: dict | None,
               home_home_ppm: float | None, away_away_ppm: float | None) -> list[Storyline]:
    """Deterministic storylines from real aggregates. Returns the strongest,
    de-duplicated by theme; the builder shows the top 3–5."""
    items: list[Storyline] = []
    lg_shots = league.get("shots") or 0
    lg_faced = league.get("shots_faced") or 0

    def conf(agg): return _confidence(agg.get("matches", 0), agg.get("matches", 0))

    for name, agg, last5, standing, home_ppm, away_ppm, is_home_side in (
        (home_name, home_agg, home_last5, home_standing, home_home_ppm, None, True),
        (away_name, away_agg, away_last5, away_standing, None, away_away_ppm, False),
    ):
        c = conf(agg)
        # Home fortress / road struggles (venue points-per-match).
        if is_home_side and home_ppm is not None and home_ppm >= 2.0:
            items.append(Storyline("STRONG_HOME", f"{name} are strong at home",
                f"{name} average {home_ppm:.1f} points per match at home this season.",
                (f"Home PPM: {home_ppm:.1f}",), "Moderate", "up", home_ppm, "venue"))
        if (not is_home_side) and away_ppm is not None and away_ppm <= 0.9:
            items.append(Storyline("WEAK_AWAY", f"{name} have struggled on the road",
                f"{name} average just {away_ppm:.1f} points per match away from home.",
                (f"Away PPM: {away_ppm:.1f}",), "Moderate", "down", 2.0 - away_ppm, "venue"))
        # Recent runs.
        if last5.get("matches", 0) >= 4 and last5.get("unbeaten"):
            items.append(Storyline("UNBEATEN_RUN", f"{name} are unbeaten in their last {last5['matches']}",
                f"{name} have not lost in their last {last5['matches']} regular-season matches "
                f"({last5['wins']}W-{last5['draws']}D).",
                (f"Last {last5['matches']}: {last5['wins']}W-{last5['draws']}D-{last5['losses']}L",),
                "Low", "up", 1.5, "form"))
        elif last5.get("matches", 0) >= 4 and last5.get("losses", 0) >= 3:
            items.append(Storyline("LOSING_RUN", f"{name} are in a rough patch",
                f"{name} have lost {last5['losses']} of their last {last5['matches']}.",
                (f"Last {last5['matches']}: {last5['wins']}W-{last5['draws']}D-{last5['losses']}L",),
                "Low", "down", 1.4, "form"))
        # Scoring surge / defensive decline (last5 vs season).
        if c and last5.get("matches", 0) >= 4 and agg.get("goals_for") is not None \
                and last5.get("goals_for", 0) - agg["goals_for"] >= 0.7:
            items.append(Storyline("SCORING_SURGE", f"{name} are scoring more lately",
                f"{name} have averaged {last5['goals_for']:.1f} goals in their last "
                f"{last5['matches']}, up from {agg['goals_for']:.1f} on the season.",
                (f"L5 GF {last5['goals_for']:.1f} vs season {agg['goals_for']:.1f}",),
                "Low", "up", 1.0, "attack_trend"))
        if c and last5.get("matches", 0) >= 4 and agg.get("goals_against") is not None \
                and last5.get("goals_against", 0) - agg["goals_against"] >= 0.7:
            items.append(Storyline("DEFENSIVE_DECLINE", f"{name} have been leaking goals",
                f"{name} have conceded {last5['goals_against']:.1f} per match lately, up from "
                f"{agg['goals_against']:.1f} on the season.",
                (f"L5 GA {last5['goals_against']:.1f} vs season {agg['goals_against']:.1f}",),
                "Low", "down", 1.0, "defense_trend"))
        # Shot volume extremes vs league.
        if c and agg.get("shots") is not None and lg_shots:
            if agg["shots"] - lg_shots >= 3:
                items.append(Storyline("HIGH_SHOT_VOLUME", f"{name} generate a lot of shots",
                    f"{name} average {agg['shots']:.1f} shots per match, above the league's {lg_shots:.1f}.",
                    (f"{agg['shots']:.1f} shots/match",), c, "up", agg["shots"] - lg_shots, "attack_volume"))
            elif lg_shots - agg["shots"] >= 3:
                items.append(Storyline("LOW_SHOT_VOLUME", f"{name} are low on shot volume",
                    f"{name} average {agg['shots']:.1f} shots per match, below the league's {lg_shots:.1f}.",
                    (f"{agg['shots']:.1f} shots/match",), c, "down", lg_shots - agg["shots"], "attack_volume"))
        # Defensive shot pressure concern.
        if c and agg.get("shots_faced") is not None and lg_faced and agg["shots_faced"] - lg_faced >= 3:
            items.append(Storyline("DEF_PRESSURE_CONCERN", f"{name} concede plenty of chances",
                f"{name} face {agg['shots_faced']:.1f} shots per match, above the league's {lg_faced:.1f}.",
                (f"{agg['shots_faced']:.1f} shots faced/match",), c, "down", agg["shots_faced"] - lg_faced, "defense"))

    # Matchup-level contrasts.
    c_both = _confidence(home_agg.get("matches", 0), away_agg.get("matches", 0))
    if c_both and home_agg.get("possession") is not None and away_agg.get("possession") is not None:
        gap = abs(home_agg["possession"] - away_agg["possession"])
        if gap >= 10:
            more = home_name if home_agg["possession"] > away_agg["possession"] else away_name
            items.append(Storyline("BALL_SHARE_CONTRAST", "A contrast in ball share",
                f"{more} tend to keep more of the ball ({max(home_agg['possession'], away_agg['possession']):.0f}% "
                f"vs {min(home_agg['possession'], away_agg['possession']):.0f}%).",
                (f"Ball share gap: {gap:.0f} pts",), c_both, "neutral", gap / 5, "possession"))
    if c_both and home_agg.get("yellows") is not None and away_agg.get("yellows") is not None:
        combined = home_agg["yellows"] + away_agg["yellows"]
        if combined >= 4.5:
            items.append(Storyline("HIGH_CARD_MATCHUP", "A card-heavy matchup",
                f"Both sides pick up cards — {combined:.1f} yellows per match combined.",
                (f"{home_name} {home_agg['yellows']:.1f} + {away_name} {away_agg['yellows']:.1f}",),
                c_both, "neutral", combined - 3, "discipline"))
    # Table position / playoff push.
    if home_standing and away_standing and home_standing.get("conference_rank") and away_standing.get("conference_rank"):
        hr, ar = home_standing["conference_rank"], away_standing["conference_rank"]
        if abs(hr - ar) >= 6:
            higher = home_name if hr < ar else away_name
            items.append(Storyline("TABLE_GAP", f"{higher} sit well above their opponent in the table",
                f"{home_name} are {_ord(hr)} and {away_name} {_ord(ar)} in the conference.",
                (f"{home_name}: {_ord(hr)}", f"{away_name}: {_ord(ar)}"), "Moderate", "neutral",
                abs(hr - ar) / 3, "table"))

    # Strongest, de-duplicated by theme.
    items.sort(key=lambda s: s.strength, reverse=True)
    seen: set[str] = set()
    unique: list[Storyline] = []
    for s in items:
        if s.theme in seen:
            continue
        seen.add(s.theme)
        unique.append(s)
    return unique[:5]


def _ord(n: int) -> str:
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"
