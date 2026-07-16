"""Builder for the MLB game page (Phase 1).

Assembles an immutable `MLBGamePage` from data strictly before the slate date.
All editorial text is composed deterministically from structured observations —
there is no free generative prose and no fabricated statistic. Sections that
cannot be computed honestly are omitted or carry an explicit note.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from components.format import format_game_time
from domain.mlb_game_page import (
    MLBGameHero, MLBGamePage, MLBGameShape, MLBIdentityMetric, MLBKeyMatchup,
    MLBPlayerTrend, MLBStoryline, MLBTeamIdentity,
)
from domain.models import DataStatus, Opportunity, OpportunityMode, SlateGame, SourceStatus
from services import mlb_analytics as A
from services.data_access import load_plate_appearances
from src.opportunity import score_hit_opportunities

ENGINE_VERSION = "mlb-game-page-v1"

# Identity vocabulary — lead adjectives read cleanly before "offense"; the second
# element is a verb phrase for a "that ..." clause.
_STRONG = {
    "Power": ("power-hitting", "does damage on extra-base hits"),
    "Contact": ("contact-oriented", "puts the ball in play and avoids empty at-bats"),
    "Plate Discipline": ("patient", "works counts and draws walks"),
    "Speed": ("aggressive", "runs and pressures defenses on the bases"),
    "RISP": ("opportunistic", "cashes in scoring chances"),
}
_WEAK = {
    "Power": "light on power",
    "Contact": "strikeout-prone",
    "Plate Discipline": "free-swinging",
    "Speed": "station-to-station",
    "RISP": "inconsistent with runners in scoring position",
}
_DIMS = ["Power", "Contact", "Plate Discipline", "Speed", "RISP"]
_DIM_KEY = {"Power": "power", "Contact": "contact", "Plate Discipline": "discipline",
            "Speed": "speed", "RISP": "risp"}


def _ordinal(n: int | None) -> str:
    if not n:
        return "—"
    n = int(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _poss(name: str) -> str:
    """Possessive that handles plural team names (Mets' / Bryce Harper's)."""
    return name + "'" if name.endswith("s") else name + "'s"


def _article(phrase: str) -> str:
    return "An" if phrase[:1].lower() in "aeiou" else "A"


def _headshot(player_id: str) -> str:
    return (f"https://img.mlbstatic.com/mlb-photos/image/upload/w_120,q_auto:best/"
            f"v1/people/{player_id}/headshot/67/current")


def _form_note(direction: str | None) -> str | None:
    return {"up": "Bats heating up", "down": "Offense cooling lately",
            "steady": "Steady at the plate"}.get(direction or "")


def _pitcher_note(k_pct: float | None, ctrl_pct: float | None) -> str | None:
    """Plain-English starter descriptor from existing K/control percentiles."""
    if k_pct is None:
        return None
    if k_pct >= 85:
        note = "Elite strikeout stuff"
    elif k_pct >= 66:
        note = "High-strikeout arm"
    elif k_pct <= 30:
        note = "Pitches to contact"
    elif ctrl_pct is not None and ctrl_pct >= 68:
        note = "Command specialist"
    else:
        note = "Balanced starter"
    # A high-strikeout arm that also limits walks earns a control tag.
    if k_pct >= 66 and ctrl_pct is not None and ctrl_pct >= 78:
        note += " · plus control"
    return note


# --------------------------------------------------------------- HERO --------
def _hero(game: SlateGame, away_ident=None, home_ident=None,
          ptable=None, away_pid=None, home_pid=None) -> MLBGameHero:
    ap, hp = game.meta.get("away_pitcher"), game.meta.get("home_pitcher")
    if ap and hp:
        status = "available"
    elif ap or hp:
        status = "partial"
    else:
        status = "unavailable"

    def _pitcher(pid):
        if ptable is not None and pid and pid in ptable.index:
            row = ptable.loc[pid]
            return float(row["k_pct"]), row["hand"], float(row["bb_suppress_pct"])
        return None, None, None

    a_k, a_hand, a_ctrl = _pitcher(away_pid)
    h_k, h_hand, h_ctrl = _pitcher(home_pid)

    def _form(ident):
        if ident is None:
            return None, None
        d = next((m.trend_direction for m in ident.metrics if m.name == "Recent Form"), None)
        return ident.recent_form_label, d

    a_form, a_dir = _form(away_ident)
    h_form, h_dir = _form(home_ident)

    return MLBGameHero(
        # Full city + team name (Baseball is tied to cities) — fall back to display.
        away_team=game.away_name or game.away_display,
        home_team=game.home_name or game.home_display,
        away_logo_url=game.away_logo, home_logo_url=game.home_logo,
        scheduled_time=format_game_time(game.start_time),
        venue=game.venue, game_status=game.status,
        probable_away_pitcher=ap, probable_home_pitcher=hp,
        probable_pitcher_status=status, league_context="MLB",
        away_form_label=a_form, away_form_dir=a_dir,
        home_form_label=h_form, home_form_dir=h_dir,
        away_pitcher_k_pct=a_k, away_pitcher_hand=a_hand,
        home_pitcher_k_pct=h_k, home_pitcher_hand=h_hand,
        away_form_note=_form_note(a_dir), home_form_note=_form_note(h_dir),
        away_pitcher_note=_pitcher_note(a_k, a_ctrl),
        home_pitcher_note=_pitcher_note(h_k, h_ctrl),
    )


# ---------------------------------------------------------- TEAM IDENTITY ----
def _identity_metric(name: str, row: pd.Series, table: pd.DataFrame) -> MLBIdentityMetric:
    key = _DIM_KEY[name]
    pct = row[key]
    rank = row.get(f"{key}_rank")
    rank = int(rank) if pd.notna(rank) else None
    pct = None if pd.isna(pct) else float(pct)
    note = None
    if name == "Power":
        raw, disp, ev = row["tb_per_pa"], f"{row['tb_per_pa']:.3f} TB/PA", "total bases per PA"
    elif name == "Contact":
        raw, disp, ev = row["hit_rate"], f"{row['hit_rate']:.3f} hit rate", "hit rate"
    elif name == "Plate Discipline":
        raw, disp, ev = row["bb_rate"], f"{row['bb_rate']:.1%} walk rate", "walk rate"
    elif name == "Speed":
        raw, disp, ev = row["attempts_per_game"], f"{row['attempts_per_game']:.2f} SB att/gm", "stolen-base attempts per game"
        if pct is None:
            note = "Limited recent baserunning sample"
    else:  # RISP
        raw, disp, ev = row["risp_tb_per_pa"], f"{row['risp_tb_per_pa']:.3f} TB/PA w/ RISP", "production with runners in scoring position"
        if pct is None:
            note = "Insufficient plate appearances with runners in scoring position"
        elif row["risp_pa"] < A.RISP_FULL:
            note = "Smaller RISP sample"
    if pct is None:
        evidence = f"Not enough data to rank {ev.split(' (')[0]}."
    else:
        evidence = f"{_ordinal(rank)} of {int(table[key].notna().sum())} in {ev}."
    return MLBIdentityMetric(name=name, raw_value=float(raw) if pd.notna(raw) else 0.0,
                             display_value=disp, league_rank=rank, percentile=pct,
                             trend_direction=None, evidence_text=evidence, sample_note=note)


def _identity_summary(ranked: list, form_dir: str | None) -> str:
    """Conversational, deterministic identity sentence; form clause differentiates teams."""
    strengths = [m for m in ranked if m.percentile is not None and m.percentile >= 66]
    vulns = [m for m in ranked if m.percentile is not None and m.percentile <= 33]
    tail = ""
    if form_dir == "up":
        tail = " The bats have been heating up lately."
    elif form_dir == "down":
        tail = " The offense has cooled off recently."
    if not strengths:
        base = ("A below-league-average offense across most categories this season"
                if len(vulns) >= 3 else
                "A balanced offense without a standout strength or glaring weakness")
        return base + "." + tail
    lead = ", ".join(_STRONG[m.name][0] for m in strengths[:2])
    clause = _STRONG[strengths[0].name][1]
    text = f"{_article(lead)} {lead} offense that {clause}"
    if vulns:
        text += f", though it can be {_WEAK[vulns[-1].name]}"
    return text + "." + tail


def _team_identity(pa: pd.DataFrame, team: str, logo: str | None, table: pd.DataFrame) -> MLBTeamIdentity:
    row = table.loc[team]
    metrics = [_identity_metric(name, row, table) for name in _DIMS]
    rf = A.recent_form(pa, team, table)
    form_metric = MLBIdentityMetric(
        name="Recent Form", raw_value=rf.last10_index, display_value=rf.label,
        league_rank=rf.rank, percentile=rf.percentile, trend_direction=rf.direction,
        evidence_text=rf.evidence,
    )
    ranked = sorted([m for m in metrics if m.percentile is not None],
                    key=lambda m: m.percentile, reverse=True)
    strengths = [m.name for m in ranked if m.percentile >= 66]
    vulns = [m.name for m in reversed(ranked) if m.percentile <= 33]
    return MLBTeamIdentity(
        team=team, logo_url=logo,
        recent_form_label=rf.label, recent_form_evidence=rf.evidence,
        metrics=tuple(metrics + [form_metric]),
        identity_summary=_identity_summary(ranked, rf.direction),
        strengths=tuple(strengths), vulnerabilities=tuple(vulns),
        sample_context=f"Season-to-date, {int(row['games'])} games, {int(row['pa']):,} PA.",
    )


# ------------------------------------------------------------ MATCHUPS -------
def _confidence(pa_faced: float) -> str:
    return "High" if pa_faced >= 300 else "Moderate" if pa_faced >= 150 else "Low"


def _pitcher_matchups(offense: str, opp_row: pd.Series, pitcher: pd.Series,
                      pitcher_name: str) -> list[tuple[float, MLBKeyMatchup]]:
    out: list[tuple[float, MLBKeyMatchup]] = []
    conf = _confidence(pitcher["pa_faced"])
    # Power vs extra-base suppression
    gap = abs(opp_row["power"] - pitcher["tb_suppress_pct"])
    edge = offense if opp_row["power"] > pitcher["tb_suppress_pct"] else pitcher_name
    out.append((gap, MLBKeyMatchup(
        title=f"Can {pitcher_name} limit {_poss(offense)} power?",
        advantage=edge, confidence=conf,
        explanation=(f"{offense} rank in the {_ordinal(int(round(opp_row['power'])))} percentile in "
                     f"extra-base production, while {pitcher_name} sits in the "
                     f"{_ordinal(int(round(pitcher['tb_suppress_pct'])))} percentile at suppressing total bases."),
        supporting_metrics=(f"{offense}: {opp_row['tb_per_pa']:.3f} TB/PA",
                            f"{pitcher_name}: {pitcher['tb_per_pa_allowed']:.3f} TB/PA allowed ({int(pitcher['pa_faced'])} PA)"),
    )))
    # Team contact vs strikeout profile
    edge = pitcher_name if pitcher["k_pct"] >= 60 and opp_row["contact"] < 50 else offense
    out.append((abs(pitcher["k_pct"] - 50) + abs(opp_row["contact"] - 50), MLBKeyMatchup(
        title=f"Can {pitcher_name} miss enough bats?",
        advantage=edge, confidence=conf,
        explanation=(f"{pitcher_name} strikes hitters out at a {pitcher['k_rate']:.1%} clip "
                     f"({_ordinal(int(round(pitcher['k_pct'])))} percentile); {offense} carry a "
                     f"{opp_row['k_rate']:.1%} strikeout rate."),
        supporting_metrics=(f"{pitcher_name}: {pitcher['k_rate']:.1%} K rate",
                            f"{offense}: {opp_row['k_rate']:.1%} K rate"),
    )))
    # Team discipline vs walk suppression
    out.append((abs(opp_row["discipline"] - 50), MLBKeyMatchup(
        title=f"Can {pitcher_name} command the strike zone?",
        advantage=offense if opp_row["discipline"] >= 60 and pitcher["bb_suppress_pct"] < 50 else pitcher_name,
        confidence=conf,
        explanation=(f"{offense} walk in {opp_row['bb_rate']:.1%} of trips; {pitcher_name} allows "
                     f"walks {'sparingly' if pitcher['bb_suppress_pct'] >= 60 else 'at a fairly typical rate'} "
                     f"({pitcher['bb_rate']:.1%})."),
        supporting_metrics=(f"{offense}: {opp_row['bb_rate']:.1%} walk rate",
                            f"{pitcher_name}: {pitcher['bb_rate']:.1%} walks allowed"),
    )))
    return out


def _handedness_matchup(pa: pd.DataFrame, offense_full: str, offense_disp: str,
                        hand: str | None, pitcher_name: str) -> tuple[float, MLBKeyMatchup] | None:
    info = A.team_vs_hand(pa, offense_full, hand)
    if not info:
        return None
    tb_diff = info["tb_per_pa"] - info["overall_tb"]
    hand_label = "left-handers" if hand == "L" else "right-handers"
    hand_side = "left" if hand == "L" else "right"
    better = "better" if tb_diff > 0 else "worse"
    strength = abs(tb_diff) * 1000
    return (strength, MLBKeyMatchup(
        title=f"How do {offense_disp} handle {hand_side}-handers?",
        advantage=offense_disp if tb_diff > 0 else pitcher_name,
        confidence="Moderate",
        explanation=(f"{offense_disp} have produced {better} against {hand_label} this season "
                     f"({info['tb_per_pa']:.3f} vs. {info['overall_tb']:.3f} TB/PA overall)."),
        supporting_metrics=(f"vs {hand_label}: {info['tb_per_pa']:.3f} TB/PA ({info['pa']} PA)",
                            f"overall: {info['overall_tb']:.3f} TB/PA"),
    ))


def _team_vs_team_matchup(away: str, away_row: pd.Series, home: str,
                          home_row: pd.Series) -> tuple[float, MLBKeyMatchup]:
    gap = abs(away_row["power"] - home_row["power"])
    edge = away if away_row["power"] > home_row["power"] else home
    return (gap, MLBKeyMatchup(
        title="Which lineup profiles stronger?",
        advantage=edge, confidence="Low",
        explanation=(f"{away} sit in the {_ordinal(int(round(away_row['power'])))} percentile for "
                     f"extra-base production, {home} in the {_ordinal(int(round(home_row['power'])))}."),
        supporting_metrics=(f"{away}: {away_row['tb_per_pa']:.3f} TB/PA",
                            f"{home}: {home_row['tb_per_pa']:.3f} TB/PA"),
        availability_note="Probable starter not matched to stored data; showing a team-level view.",
    ))


def _build_matchups(pa, away, home, a_disp, h_disp, table, ptable, away_pid, home_pid,
                    away_pname, home_pname) -> list[MLBKeyMatchup]:
    cands: list[tuple[float, MLBKeyMatchup]] = []
    away_row, home_row = table.loc[away], table.loc[home]
    # away offense vs home starter
    if home_pid and home_pid in ptable.index:
        p = ptable.loc[home_pid]
        cands += _pitcher_matchups(a_disp, away_row, p, home_pname or "the starter")
        h = _handedness_matchup(pa, away, a_disp, p["hand"], home_pname or "the starter")
        if h:
            cands.append(h)
    if away_pid and away_pid in ptable.index:
        p = ptable.loc[away_pid]
        cands += _pitcher_matchups(h_disp, home_row, p, away_pname or "the starter")
        h = _handedness_matchup(pa, home, h_disp, p["hand"], away_pname or "the starter")
        if h:
            cands.append(h)
    if not cands:  # neither starter matched
        cands.append(_team_vs_team_matchup(a_disp, away_row, h_disp, home_row))
    cands.sort(key=lambda c: c[0], reverse=True)
    return [m for _, m in cands[:5]]


# ------------------------------------------------------------ TRENDS ---------
def _trend_from_row(r: pd.Series, direction: str) -> MLBPlayerTrend:
    comps = {"total bases per PA": (r["r_tb"], r["b_tb"]), "hit rate": (r["r_hit"], r["b_hit"]),
             "on-base rate": (r["r_reach"], r["b_reach"])}
    best_name, best_change = None, 0.0
    for name, (rv, bv) in comps.items():
        if bv:
            ch = (rv - bv) / bv
            if (direction == "up" and ch > best_change) or (direction == "down" and ch < best_change):
                best_name, best_change = name, ch
    if best_name is None:
        best_name, best_change = "total bases per PA", (r["r_tb"] - r["b_tb"])
    verb = "up" if best_change > 0 else "down"
    k_note = ""
    if direction == "down" and r["r_k"] > r["b_k"] + 0.03:
        k_note = f" His strikeout rate has climbed to {r['r_k']:.0%}."
    elif direction == "up" and r["r_k"] < r["b_k"] - 0.03:
        k_note = f" He has trimmed his strikeout rate to {r['r_k']:.0%}."
    expl = (f"{best_name[:1].upper() + best_name[1:]} is {verb} {abs(best_change):.0%} over his prior "
            f"baseline, with hits in {int(r['hit_games'])} of his last {int(r['recent_games'])} games.{k_note}")
    return MLBPlayerTrend(
        player_id=r["player_id"], player_name=r["player_name"], team=r["team"],
        headshot_url=_headshot(r["player_id"]), direction=direction,
        trend_score=float(r["trend_score"]),
        recent_window=f"last {int(r['recent_games'])} games ({int(r['recent_pa'])} PA)",
        baseline_window=f"season baseline ({int(r['baseline_pa'])} PA)",
        recent_summary=f"{r['r_hit']:.3f} hit rate · {r['r_tb']:.3f} TB/PA",
        baseline_summary=f"{r['b_hit']:.3f} hit rate · {r['b_tb']:.3f} TB/PA",
        explanation=expl, sample_size=int(r["recent_pa"]),
    )


def _build_trends(pa, teams) -> tuple[tuple[MLBPlayerTrend, ...], tuple[MLBPlayerTrend, ...]]:
    df = A.player_trend_frame(pa, teams)
    if df.empty:
        return (), ()
    heating = df[df["trend_score"] >= A.TREND_MAGNITUDE].sort_values("trend_score", ascending=False).head(3)
    cooling = df[df["trend_score"] <= -A.TREND_MAGNITUDE].sort_values("trend_score").head(3)
    return (tuple(_trend_from_row(r, "up") for _, r in heating.iterrows()),
            tuple(_trend_from_row(r, "down") for _, r in cooling.iterrows()))


# --------------------------------------------------------- OPPORTUNITIES -----
def _build_opportunities(pa, game: SlateGame, teams: list[str]) -> tuple[Opportunity, ...]:
    scored = score_hit_opportunities(pa, teams)
    if scored.empty:
        return ()
    logos = {str(n): logo for n, logo in
             ((game.away_name, game.away_logo), (game.home_name, game.home_logo)) if n and logo}
    out = []
    for _, row in scored.head(6).iterrows():
        pid = str(int(row.batter_id))
        out.append(Opportunity(
            league="MLB", player_id=pid, player_name=str(row.player),
            team_id=None, team_name=str(row.team), market="1+ Hit", threshold=1,
            opportunity_score=int(row.opportunity_score), stability_score=int(row.stability_score),
            supporting_evidence=list(row.support) if isinstance(row.support, list) else [],
            negative_evidence=list(row.risks) if isinstance(row.risks, list) else [],
            image_url=logos.get(str(row.team)),          # team logo (recognition)
            headshot_url=_headshot(pid),                 # player headshot (identity)
            mode=OpportunityMode.SLATE,
            components={"last_25_hit_rate": float(row.last_25_hit_rate),
                        "last_50_hit_rate": float(row.last_50_hit_rate),
                        "pa_per_game": float(row.pa_per_game), "k_rate": float(row.k_rate)},
        ))
    return tuple(out)


# --------------------------------------------------------- GAME SHAPE --------
def _starter_dominance(ptable, pid) -> float | None:
    if not pid or pid not in ptable.index:
        return None
    p = ptable.loc[pid]
    return float((p["k_pct"] + p["bb_suppress_pct"] + p["hit_suppress_pct"] + p["tb_suppress_pct"]) / 4)


def _game_shape(table, away, home, a_disp, h_disp, away_dom, home_dom, away_form, home_form) -> MLBGameShape | None:
    ar, hr = table.loc[away], table.loc[home]
    offense_power = (ar["power"] + hr["power"]) / 2
    offense_contact = (ar["contact"] + hr["contact"]) / 2
    doms = [d for d in (away_dom, home_dom) if d is not None]
    facts: list[str] = []
    if len(doms) == 2:
        starter_dom = sum(doms) / 2
        facts.append(f"Both probable starters grade around the {_ordinal(int(round(starter_dom)))} "
                     "percentile in combined suppression.")
        if starter_dom >= 60 and offense_power < 50:
            label, driver, conf = "Starter-driven", "Pitching and command", "Moderate"
            shape = "Runs may be at a premium if the starters hold form."
        elif offense_power >= 60:
            label, driver, conf = "Power-oriented", "Extra-base damage", "Moderate"
            shape = "Both lineups can change the game with one swing."
        elif offense_contact >= 60 and offense_power < 45:
            label, driver, conf = "Contact-heavy", "Traffic and situational hitting", "Moderate"
            shape = "Offense likely comes from stringing hits together."
        else:
            label, driver, conf = "Balanced", "No single dominant factor", "Low"
            shape = "Competitive profile without a clear stylistic tilt."
    else:
        label, driver, conf = "Uncertain", "Unclear without matched starters", "Low"
        shape = "Probable-starter data is incomplete, so the shape is hard to call."
        facts.append("At least one probable starter could not be matched to stored data.")
    # Early edge: better offense-vs-opposing-starter attack.
    away_attack = (ar["power"] + ar["contact"] + ar["discipline"]) / 3 - (home_dom or 50)
    home_attack = (hr["power"] + hr["contact"] + hr["discipline"]) / 3 - (away_dom or 50)
    early_edge = a_disp if away_attack > home_attack else h_disp
    volatility = "Elevated" if (away_form == "up" and home_form == "down") or (away_form == "down" and home_form == "up") else "Moderate"
    facts.append(f"{a_disp} are trending {away_form}; {h_disp} are trending {home_form}.")

    # Plain-English narrative read (presentation; from the same numbers).
    narrative: list[str] = [f"{label} matchup.", shape]
    if away_form == "up" and home_form != "up":
        narrative.append(f"{a_disp} bring stronger recent momentum.")
    elif home_form == "up" and away_form != "up":
        narrative.append(f"{h_disp} bring stronger recent momentum.")
    if abs(ar["power"] - hr["power"]) >= 12:
        stronger = a_disp if ar["power"] > hr["power"] else h_disp
        narrative.append(f"{stronger} bring more power.")
    if len(doms) == 2 and sum(doms) / 2 >= 58:
        narrative.append("Starting pitching is likely to set the tone.")

    return MLBGameShape(label=label, confidence=conf, early_edge=early_edge,
                        offensive_driver=driver, volatility=volatility, likely_shape=shape,
                        supporting_facts=tuple(facts), narrative=tuple(narrative))


# --------------------------------------------------------- STORYLINES --------
def _build_storylines(away_id, home_id, heating, cooling, away_dom, home_dom,
                      table, away, home, a_disp, h_disp, away_pname, home_pname) -> tuple[MLBStoryline, ...]:
    cands: list[MLBStoryline] = []
    ar, hr = table.loc[away], table.loc[home]
    disp = {away: a_disp, home: h_disp}
    # Heating standout
    if heating:
        h = heating[0]
        cands.append(MLBStoryline(
            title=f"Is {h.player_name} the one to watch?",
            explanation=f"{h.player_name} enters as {_poss(disp.get(h.team, h.team))} hottest bat. {h.explanation}",
            supporting_facts=(h.recent_summary, h.baseline_summary), priority=abs(h.trend_score) * 20))
    if cooling:
        c = cooling[0]
        cands.append(MLBStoryline(
            title=f"Can {c.player_name} snap out of it?",
            explanation=f"{c.player_name} has cooled off. {c.explanation}",
            supporting_facts=(c.recent_summary, c.baseline_summary), priority=abs(c.trend_score) * 18))
    # Starter K vs opposing contact
    for pid, pname, offense_row, offense in ((home_id, home_pname, ar, a_disp), (away_id, away_pname, hr, h_disp)):
        dom = home_dom if pid == home_id else away_dom
        if pid and dom is not None and offense_row["contact"] < 40:
            cands.append(MLBStoryline(
                title=f"Can {offense} handle {pname}'s strikeout stuff?",
                explanation=(f"{offense} have been a below-average contact team while {pname} misses "
                             "bats at an above-average rate — a swing factor early."),
                supporting_facts=(f"{offense} contact percentile: {int(round(offense_row['contact']))}",),
                priority=(50 - offense_row["contact"]) + (dom - 50)))
    # Power vs suppression gap
    gap = abs(ar["power"] - hr["power"])
    if gap >= 35:
        stronger = a_disp if ar["power"] > hr["power"] else h_disp
        cands.append(MLBStoryline(
            title=f"Does {_poss(stronger)} power tilt the game?",
            explanation=f"{stronger} bring a clearly stronger extra-base profile into this matchup.",
            supporting_facts=(f"{a_disp} power pct {int(round(ar['power']))} vs {h_disp} {int(round(hr['power']))}",),
            priority=gap))
    cands.sort(key=lambda s: s.priority, reverse=True)
    strong = [s for s in cands if s.priority >= 12]
    return tuple(strong[:3]) if len(strong) >= 2 else tuple(cands[:2])


# --------------------------------------------------------- STORY -------------
def _game_story(a_disp, h_disp, away_ident, home_ident, matchups, away_form, home_form) -> tuple[str, ...]:
    """Three role-ordered insights: Biggest Advantage, Swing Factor, Momentum."""
    s: list[str] = []
    # 1) Biggest Advantage — the defining identity contrast.
    a_str = away_ident.strengths[0] if away_ident.strengths else None
    h_str = home_ident.strengths[0] if home_ident.strengths else None
    if a_str and h_str and a_str != h_str:
        s.append(f"{h_disp} bring the more {_STRONG[h_str][0]} profile, while {a_disp} lean on being "
                 f"{_STRONG[a_str][0]}.")
    elif h_str:
        s.append(f"{_poss(h_disp)} offense is defined by being {_STRONG[h_str][0]}, and this game tests "
                 f"whether {a_disp} can match it.")
    elif a_str:
        s.append(f"{_poss(a_disp)} offense is defined by being {_STRONG[a_str][0]}, and this game tests "
                 f"whether {h_disp} can match it.")
    else:
        s.append("Neither offense enters with a dominant identity, so early execution matters most.")
    # 2) Swing Factor — the top matchup.
    if matchups:
        s.append(matchups[0].explanation)
    # 3) Momentum — recent form, or the weaker side's path if both steady.
    if away_form != "steady" or home_form != "steady":
        s.append(f"{a_disp} are {away_ident.recent_form_label.lower()} and {h_disp} are "
                 f"{home_ident.recent_form_label.lower()} over their last 10 games.")
    else:
        away_weaker = _overall(away_ident) < _overall(home_ident)
        weaker_disp = a_disp if away_weaker else h_disp
        weaker_ident = away_ident if away_weaker else home_ident
        if weaker_ident.strengths:
            s.append(f"For {weaker_disp}, the path runs through being {_STRONG[weaker_ident.strengths[0]][0]}.")
    return tuple(s[:3])


def _overall(ident: MLBTeamIdentity) -> float:
    vals = [m.percentile for m in ident.metrics if m.percentile is not None and m.name != "Recent Form"]
    return sum(vals) / len(vals) if vals else 50.0


# --------------------------------------------------------- ENTRY POINT -------
def build_mlb_game_page(game: SlateGame, slate_date: date, as_of: date,
                        pa: pd.DataFrame | None = None) -> MLBGamePage:
    if pa is None:
        pa = load_plate_appearances(as_of=as_of)
    away, home = game.away_name, game.home_name
    a_disp = game.away_short or away
    h_disp = game.home_short or home
    hero = _hero(game)
    context = (f"Based on plate appearances before {as_of.isoformat()}. Confirmed lineups, "
               "injuries, weather, bullpen availability, and park factors are not yet included.")
    data_status = DataStatus(source="Plate-appearance feed", status=SourceStatus.LIVE,
                             fetched_at=datetime.now(), detail=context)

    if pa.empty or away not in set(pa["batting_team"]) or home not in set(pa["batting_team"]):
        # Not enough stored data for these teams — return a hero-only page.
        empty = MLBTeamIdentity(away or "", game.away_logo, "—", "", (), "Not enough stored data.", (), (), "")
        return MLBGamePage(hero=hero, game_story=(), away_identity=empty,
                           home_identity=MLBTeamIdentity(home or "", game.home_logo, "—", "", (), "Not enough stored data.", (), (), ""),
                           key_matchups=(), heating_up=(), cooling_off=(), opportunities=(),
                           game_shape=None, storylines=(), data_status=data_status,
                           generated_at=datetime.now().isoformat(timespec="seconds"),
                           as_of=as_of.isoformat())

    table = A.team_metric_table(pa)
    ptable = A.pitcher_league_table(pa)
    away_pid = A.match_pitcher(pa, game.meta.get("away_pitcher"))
    home_pid = A.match_pitcher(pa, game.meta.get("home_pitcher"))

    away_ident = _team_identity(pa, away, game.away_logo, table)
    home_ident = _team_identity(pa, home, game.home_logo, table)
    # Enrich the hero into a game summary (form + starter K-percentile/hand).
    hero = _hero(game, away_ident, home_ident, ptable, away_pid, home_pid)
    matchups = _build_matchups(pa, away, home, a_disp, h_disp, table, ptable, away_pid, home_pid,
                               game.meta.get("away_pitcher"), game.meta.get("home_pitcher"))
    heating, cooling = _build_trends(pa, [away, home])
    opportunities = _build_opportunities(pa, game, [away, home])
    away_dom, home_dom = _starter_dominance(ptable, away_pid), _starter_dominance(ptable, home_pid)
    a_form = away_ident.metrics[-1].trend_direction
    h_form = home_ident.metrics[-1].trend_direction
    shape = _game_shape(table, away, home, a_disp, h_disp, away_dom, home_dom, a_form, h_form)
    storylines = _build_storylines(away_pid, home_pid, heating, cooling, away_dom, home_dom,
                                   table, away, home, a_disp, h_disp,
                                   game.meta.get("away_pitcher"), game.meta.get("home_pitcher"))
    story = _game_story(a_disp, h_disp, away_ident, home_ident, matchups, a_form, h_form)

    return MLBGamePage(
        hero=hero, game_story=story, away_identity=away_ident, home_identity=home_ident,
        key_matchups=tuple(matchups), heating_up=heating, cooling_off=cooling,
        opportunities=opportunities, game_shape=shape, storylines=storylines,
        data_status=data_status, generated_at=datetime.now().isoformat(timespec="seconds"),
        as_of=as_of.isoformat())
