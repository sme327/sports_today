"""Builder for the WNBA matchup page.

Assembles an immutable WNBAGamePage from player game logs strictly before the
slate date. All editorial text is composed deterministically from structured
observations; sections degrade gracefully when data is thin.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from components.format import format_game_time
from domain.models import DataStatus, Opportunity, OpportunityMode, SlateGame, SourceStatus
from domain.wnba_game_page import (
    WNBABattlefield, WNBAFeatured, WNBAGamePage, WNBAHero, WNBAMetric,
    WNBAPlayerTrend, WNBAShapePlayer, WNBASnapshot, WNBASpark, WNBATeamIdentity,
    WNBATeamTrends,
)
from services import wnba_analytics as A
from services.data_access import load_wnba_player_logs
from src.wnba_opportunity import score_wnba_opportunities

ENGINE_VERSION = "wnba-game-page-v1"

# Identity label -> (percentile column, adjective, supporting stat key/format).
_LABELS = [
    ("Elite offense", "off_pct", lambda r: f"{r.pts_for:.1f} PPG"),
    ("Defensive-minded", "def_pct", lambda r: f"{r.pts_against:.1f} allowed"),
    ("Three-point shooting", "three_pct", lambda r: f"{r.tpm_pg:.1f} 3PM at {r.tp_pct:.0%}"),
    ("Transition team", "pace_pct", lambda r: f"{r.scoring_pace:.0f} combined-scoring pace"),
    ("Paint-first offense", "paint_pct", lambda r: f"{r.two_pt_pg:.1f} two-point makes"),
    ("Ball movement", "ballmove_pct", lambda r: f"{r.ast_pg:.1f} assists"),
    ("Rebounding", "reb_pct", lambda r: f"{r.reb_margin:+.1f} rebound margin"),
    ("Rim protection", "rim_pct", lambda r: f"{r.blk_pg:.1f} blocks"),
]
_WEAK = {"Elite offense": "an inconsistent offense", "Defensive-minded": "a leaky defense",
         "Three-point shooting": "limited outside shooting", "Transition team": "a slower half-court style",
         "Paint-first offense": "little interior scoring", "Ball movement": "an iso-heavy offense",
         "Rebounding": "a rebounding disadvantage", "Rim protection": "little rim protection"}


def _headshot_ok(v) -> str | None:
    return v if isinstance(v, str) and v else None


def _ordinal(n) -> str:
    if n is None:
        return "—"
    n = int(round(n))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


# ------------------------------------------------------------ IDENTITY -------
def _team_labels(row) -> list[tuple[str, float]]:
    out = []
    for name, col, _ in _LABELS:
        pct = row.get(col)
        if pct is not None and not pd.isna(pct) and pct >= 66:
            out.append((name, float(pct)))
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def _identity(tt, tg, tid, logo) -> WNBATeamIdentity:
    row = tt.loc[tid]
    labels = _team_labels(row)
    label_names = tuple(n for n, _ in labels)
    metrics = []
    for name, col, fmt in _LABELS:
        pct = row.get(col)
        rank = int(tt[col].rank(ascending=False, method="min").loc[tid]) if col in tt else None
        metrics.append(WNBAMetric(
            name=name.replace(" offense", "").replace("-minded", " D").replace(" team", "").replace(" offense", ""),
            display_value=fmt(row),
            percentile=None if pct is None or pd.isna(pct) else float(pct),
            league_rank=rank,
            evidence_text=f"{_ordinal(rank)} of {len(tt)} in the league sample",
        ))
    # Vulnerabilities: dimensions in the bottom third.
    vulns = []
    for name, col, _ in _LABELS:
        pct = row.get(col)
        if pct is not None and not pd.isna(pct) and pct <= 33:
            vulns.append((name, float(pct)))
    vulns.sort(key=lambda x: x[1])
    vuln_names = tuple(n for n, _ in vulns)
    # Summary sentence.
    if label_names:
        lead = " and ".join(_short_label(n) for n in label_names[:2])
        summary = f"{lead.capitalize()}"
        if vuln_names:
            summary += f", though hampered by {_WEAK.get(vuln_names[0], 'clear weaknesses')}"
        summary += "."
    else:
        summary = "A balanced team without a defining strength or glaring weakness."
    rf = A.recent_form(tg, tid)
    return WNBATeamIdentity(
        team=row.team, logo=logo, record=f"{int(row.wins)}-{int(row.losses)}",
        labels=label_names, summary=summary, metrics=tuple(metrics),
        strengths=label_names, vulnerabilities=vuln_names,
        sample_context=f"Season-to-date, {int(row.games)} games.",
        form_results=rf.get("results", ()), streak=rf.get("streak", "—"))


def _short_label(name: str) -> str:
    return {"Elite offense": "an elite offense", "Defensive-minded": "a defensive identity",
            "Three-point shooting": "a three-point attack", "Transition team": "a transition game",
            "Paint-first offense": "a paint-first attack", "Ball movement": "sharp ball movement",
            "Rebounding": "a rebounding edge", "Rim protection": "strong rim protection"}.get(name, name.lower())


# --------------------------------------------------------- SNAPSHOT ----------
def _snapshot(tt, tg, tid, game_date, opp_id) -> tuple[WNBASnapshot, ...]:
    rf = A.recent_form(tg, tid)
    rest = A.rest_days(tg, tid, game_date)
    series = A.season_series(tg, tid, opp_id)
    cards = [
        WNBASnapshot("Last 5", rf.get("record", "—"), "".join(rf.get("results", ()))),
        WNBASnapshot("Streak", rf.get("streak", "—")),
        WNBASnapshot("L5 scoring", f"{rf.get('pts_for', 0):.1f}", "points/game"),
        WNBASnapshot("L5 defense", f"{rf.get('pts_against', 0):.1f}", "allowed/game"),
        WNBASnapshot("Home", rf.get("home_record", "—"), "Road " + rf.get("road_record", "—")),
        WNBASnapshot("Rest", f"{rest}d" if rest is not None else "—", "since last game"),
    ]
    if series.get("played"):
        cards.append(WNBASnapshot("Series", f"{series['away_wins']}-{series['home_wins']}",
                                  f"{series['played']} played"))
    return tuple(cards)


# --------------------------------------------------------- BATTLEFIELDS ------
def _conf(games) -> str:
    return "High" if games >= 20 else "Moderate" if games >= 10 else "Low"


def _battlefields(tt, a_id, h_id, a_disp, h_disp) -> tuple[WNBABattlefield, ...]:
    a, h = tt.loc[a_id], tt.loc[h_id]
    conf = _conf(min(a.games, h.games))
    cands: list[tuple[float, WNBABattlefield]] = []

    # Tempo
    gap = abs(a.pace_pct - h.pace_pct)
    faster = a_disp if a.scoring_pace > h.scoring_pace else h_disp
    cands.append((gap, WNBABattlefield(
        title="Tempo", advantage=faster, confidence=conf,
        explanation=(f"{a_disp} play at a {a.scoring_pace:.0f} combined-scoring pace, {h_disp} at "
                     f"{h.scoring_pace:.0f}. A faster game favors {faster}."),
        supporting_metrics=(f"{a_disp}: {a.scoring_pace:.0f} pace ({_ordinal(int(round(a.pace_pct)))} pct)",
                            f"{h_disp}: {h.scoring_pace:.0f} pace ({_ordinal(int(round(h.pace_pct)))} pct)"))))
    # Perimeter: each offense's 3PT vs opponent's 3PT defense
    a_edge = a.three_pct - (100 - h.perimeter_def_pct)
    h_edge = h.three_pct - (100 - a.perimeter_def_pct)
    p_adv = a_disp if a_edge > h_edge else h_disp
    cands.append((abs(a_edge - h_edge), WNBABattlefield(
        title="Perimeter", advantage=p_adv, confidence=conf,
        explanation=(f"{a_disp} shoot {a.tp_pct:.0%} from three ({a.tpm_pg:.1f}/gm); {h_disp} allow "
                     f"{h.opp_tp_pct:.0%}. The three-point battle tilts toward {p_adv}."),
        supporting_metrics=(f"{a_disp}: {a.tpm_pg:.1f} 3PM at {a.tp_pct:.0%}",
                            f"{h_disp} allow {h.opp_tp_pct:.0%} on threes"))))
    # Paint / interior vs rim protection
    paint_adv = a_disp if (a.paint_pct - h.rim_pct) > (h.paint_pct - a.rim_pct) else h_disp
    cands.append((abs(a.paint_pct - h.paint_pct) + abs(a.rim_pct - h.rim_pct), WNBABattlefield(
        title="Paint", advantage=paint_adv, confidence=conf,
        explanation=(f"{a_disp} score {a.two_pt_pg:.1f} two-point makes a game; {h_disp} protect the rim "
                     f"with {h.blk_pg:.1f} blocks. Interior control leans {paint_adv}."),
        supporting_metrics=(f"{a_disp}: {a.two_pt_pg:.1f} 2PT makes",
                            f"{h_disp}: {h.blk_pg:.1f} blocks/gm"))))
    # Turnovers: ball security vs pressure
    to_adv = a_disp if a.tov_pg < h.tov_pg else h_disp
    cands.append((abs(a.security_pct - h.security_pct), WNBABattlefield(
        title="Turnovers", advantage=to_adv, confidence=conf,
        explanation=(f"{a_disp} average {a.tov_pg:.1f} turnovers, {h_disp} {h.tov_pg:.1f}; steals "
                     f"({a.stl_pg:.1f} vs {h.stl_pg:.1f}) add pressure. Ball security favors {to_adv}."),
        supporting_metrics=(f"{a_disp}: {a.tov_pg:.1f} TO / {a.stl_pg:.1f} STL",
                            f"{h_disp}: {h.tov_pg:.1f} TO / {h.stl_pg:.1f} STL"))))
    # Rebounding
    reb_adv = a_disp if a.reb_margin > h.reb_margin else h_disp
    cands.append((abs(a.reb_pct - h.reb_pct), WNBABattlefield(
        title="Rebounding", advantage=reb_adv, confidence=conf,
        explanation=(f"{a_disp} carry a {a.reb_margin:+.1f} rebound margin, {h_disp} {h.reb_margin:+.1f}. "
                     f"Second-chance control leans {reb_adv}."),
        supporting_metrics=(f"{a_disp}: {a.reb_margin:+.1f} margin, {a.oreb_pg:.1f} OREB",
                            f"{h_disp}: {h.reb_margin:+.1f} margin, {h.oreb_pg:.1f} OREB"))))
    cands.sort(key=lambda c: c[0], reverse=True)
    return tuple(m for _, m in cands[:5])


# --------------------------------------------------------- GAME SCRIPT -------
def _game_script(tt, a_id, h_id, a_disp, h_disp, battlefields) -> tuple[str, ...]:
    a, h = tt.loc[a_id], tt.loc[h_id]
    pace = (a.pace_pct + h.pace_pct) / 2
    three = (a.three_pct + h.three_pct) / 2
    defense = (a.def_pct + h.def_pct) / 2
    paint = (a.paint_pct + h.paint_pct) / 2
    if pace >= 62 and three >= 58:
        style = "a fast-paced, perimeter-oriented matchup"
    elif pace >= 62:
        style = "an up-tempo, high-scoring matchup"
    elif defense >= 62 and pace < 45:
        style = "a defensive, grind-it-out battle"
    elif abs(a.off_pct - h.off_pct) >= 35 or abs(a.def_pct - h.def_pct) >= 35:
        style = "a clash of contrasting styles"
    elif paint >= 60:
        style = "a paint-oriented, physical matchup"
    else:
        style = "a balanced, competitive matchup"
    s = [f"Expect {style}. {a_disp} ({a.pts_for:.1f} PPG) meet {h_disp} ({h.pts_for:.1f} PPG), with "
         f"{'both defenses stingy' if defense >= 60 else 'points likely on both ends'}."]
    if battlefields:
        s.append(f"The game likely turns on {battlefields[0].title.lower()}: {battlefields[0].explanation}")
    return tuple(s)


# --------------------------------------------------------- PLAYERS -----------
def _impact(r) -> float:
    return r.ppg + 1.2 * r.apg + 1.0 * (r.spg + r.bpg) + 0.7 * r.rpg


def _role(r) -> str:
    if r.ppg >= 17 and r.apg >= 4.5:
        return "Superstar"
    if r.ppg >= 16:
        return "Primary scorer"
    if r.apg >= 5:
        return "Primary creator"
    if r.bpg >= 1.5 or (str(r.position) in ("C", "F-C")):
        return "Defensive anchor"
    if r.tpm_pg >= 2.2:
        return "Floor spacer"
    if r.rpg >= 8:
        return "Rebounding presence"
    return "Key contributor"


def _shape_players(pf, trend_lookup, a_id, h_id) -> tuple[WNBAShapePlayer, ...]:
    if pf.empty:
        return ()
    pf = pf.copy()
    pf["impact"] = pf.apply(_impact, axis=1)
    out = []
    for tid in (a_id, h_id):
        team_pf = pf[pf.team_id == str(tid)].sort_values("impact", ascending=False).head(2)
        for _, r in team_pf.iterrows():
            role = _role(r)
            trend = trend_lookup.get(r.player_id, "Holding steady")
            strengths = []
            if r.ppg >= 15:
                strengths.append("scoring")
            if r.apg >= 4:
                strengths.append("playmaking")
            if r.rpg >= 7:
                strengths.append("rebounding")
            if r.bpg + r.spg >= 2:
                strengths.append("defense")
            if r.tpm_pg >= 2:
                strengths.append("outside shooting")
            out.append(WNBAShapePlayer(
                player_id=r.player_id, name=r.player_name, team=r.team,
                headshot=_headshot_ok(r.headshot), position=r.position, role=role,
                season_line=f"{r.ppg:.1f} PPG · {r.rpg:.1f} REB · {r.apg:.1f} AST · {r.mpg:.0f} MIN",
                trend=trend, strengths=", ".join(strengths[:3]) or "all-around impact",
                why_tonight=f"As {r.team}'s {role.lower()}, {r.player_name.split()[-1]} sets the tone "
                            f"for how they attack."))
    return tuple(out)


def _trend_category(r, direction) -> str:
    if direction == "up":
        if r.d_min >= 6:
            return "Expanded Role"
        if r.b_pts < 9 and r.r_pts >= 13:
            return "Potential Breakout"
        return "Trending Up"
    return "Recent Slump" if r.r_pts < r.b_pts - 4 else "Trending Down"


def _player_trends(tf) -> tuple[tuple, tuple]:
    if tf.empty:
        return (), ()

    def mk(r, direction):
        cat = _trend_category(r, direction)
        moved = "points" if abs(r.d_pts) >= abs(r.d_min) / 3 else "minutes"
        if moved == "points":
            expl = f"{r.r_pts:.1f} points over his last {int(r.recent_games)} (from {r.b_pts:.1f})."
        else:
            expl = f"Minutes {'up' if r.d_min > 0 else 'down'} to {r.r_min:.1f} from {r.b_min:.1f}."
        return WNBAPlayerTrend(
            player_id=r.player_id, name=r.player_name, team=r.team,
            headshot=_headshot_ok(r.headshot), position=r.position,
            direction=direction, category=cat,
            recent_summary=f"L{int(r.recent_games)}: {r.r_pts:.1f}p {r.r_reb:.1f}r {r.r_ast:.1f}a",
            baseline_summary=f"Season: {r.b_pts:.1f}p {r.b_min:.1f} min",
            explanation=expl)
    up = tf[tf.trend_score >= A.TREND_MAGNITUDE].sort_values("trend_score", ascending=False).head(3)
    down = tf[tf.trend_score <= -A.TREND_MAGNITUDE].sort_values("trend_score").head(3)
    return (tuple(mk(r, "up") for _, r in up.iterrows()),
            tuple(mk(r, "down") for _, r in down.iterrows()))


# --------------------------------------------------------- TEAM TRENDS -------
def _team_trends(tg, tid, team, logo, n: int = 8) -> WNBATeamTrends:
    g = tg[tg.team_id == tid].sort_values("game_date").tail(n)
    def spark(label, series, fmt):
        vals = tuple(float(v) for v in series if pd.notna(v))
        disp = fmt(vals[-1]) if vals else "—"
        return WNBASpark(label=label, values=vals, display=disp)
    sparks = (
        spark("Points", g["pts_for"], lambda v: f"{v:.0f}"),
        spark("Opp points", g["pts_against"], lambda v: f"{v:.0f}"),
        spark("3PT%", g["tp_pct"] * 100, lambda v: f"{v:.0f}%"),
        spark("Rebounds", g["reb"], lambda v: f"{v:.0f}"),
    )
    return WNBATeamTrends(team=team, logo=logo, sparks=sparks)


# --------------------------------------------------------- OPPORTUNITIES -----
def _opportunities(logs, game: SlateGame, tt, a_id, h_id) -> tuple[Opportunity, ...]:
    teams = {str(a_id), str(h_id)}
    for v in (game.away_abbr, game.home_abbr, game.away_name, game.home_name):
        if v:
            teams.add(str(v))
    scored = score_wnba_opportunities(logs, teams)
    if scored.empty:
        return ()
    logos = {}
    for tid, logo in ((a_id, game.away_logo), (h_id, game.home_logo)):
        logos[str(tid)] = logo
    out = []
    for _, row in scored.head(6).iterrows():
        support = list(row.support) if isinstance(row.support, list) else []
        risks = list(row.risks) if isinstance(row.risks, list) else []
        out.append(Opportunity(
            league="WNBA", player_id=str(row.player_id), player_name=str(row.player),
            team_id=str(row.team_id) if row.team_id else None, team_name=str(row.team),
            market=str(row.display_market), threshold=row.threshold,
            opportunity_score=int(row.opportunity_score), stability_score=int(row.stability_score),
            supporting_evidence=support, negative_evidence=risks,
            image_url=logos.get(str(row.team_id)),
            headshot_url=_headshot_ok(row.headshot), mode=OpportunityMode.SLATE))
    return tuple(out)


# --------------------------------------------------------- HERO --------------
def _featured(pf, tid) -> WNBAFeatured | None:
    team_pf = pf[pf.team_id == str(tid)]
    if team_pf.empty:
        return None
    team_pf = team_pf.copy()
    team_pf["impact"] = team_pf.apply(_impact, axis=1)
    r = team_pf.sort_values("impact", ascending=False).iloc[0]
    return WNBAFeatured(player_id=r.player_id, name=r.player_name, headshot=_headshot_ok(r.headshot),
                        line=f"{r.ppg:.1f} PPG · {r.rpg:.1f} REB · {r.apg:.1f} AST")


# --------------------------------------------------------- ENTRY POINT -------
def build_wnba_game_page(game: SlateGame, slate_date: date, as_of: date,
                         logs: pd.DataFrame | None = None) -> WNBAGamePage:
    if logs is None:
        logs = load_wnba_player_logs(as_of=as_of)
    a_disp = game.away_short or game.away_name or "Away"
    h_disp = game.home_short or game.home_name or "Home"
    context = (f"Based on games before {as_of.isoformat()}. Injuries, confirmed starters, rest/travel, "
               "and advanced ratings (pace, offensive/defensive rating) are not yet included.")
    data_status = DataStatus(source="ESPN box scores", status=SourceStatus.LIVE,
                             fetched_at=datetime.now(), detail=context)

    def hero_only(reason: str) -> WNBAGamePage:
        empty = WNBATeamIdentity(a_disp, game.away_logo, "—", (), reason, (), (), (), "", (), "—")
        empty_h = WNBATeamIdentity(h_disp, game.home_logo, "—", (), reason, (), (), (), "", (), "—")
        hero = WNBAHero(a_disp, h_disp, game.away_logo, game.home_logo, "—", "—",
                        format_game_time(game.start_time), game.venue, None, None, None,
                        game.state, game.away_score, game.home_score, game.status_detail)
        return WNBAGamePage(hero, (), (), (), empty, empty_h, (), (), (), (), None, None, (),
                            data_status, datetime.now().isoformat(timespec="seconds"), as_of.isoformat())

    if logs.empty:
        return hero_only("Not enough collected WNBA data yet.")

    tg = A.team_game_frame(logs)
    tt = A.team_season_table(tg)
    # Match the scheduled teams to team_ids present in the logs (by id/abbr/name token).
    a_id = _match_team(tt, game.away_id, game.away_abbr, game.away_name)
    h_id = _match_team(tt, game.home_id, game.home_abbr, game.home_name)
    if a_id is None or h_id is None or a_id not in tt.index or h_id not in tt.index:
        return hero_only("One or both teams have no collected game data yet.")

    pf = A.player_season_frame(logs, [a_id, h_id])
    tf = A.player_trend_frame(logs, [a_id, h_id])
    trend_lookup = {}
    if not tf.empty:
        for _, r in tf.iterrows():
            trend_lookup[r.player_id] = ("Trending up" if r.trend_score >= A.TREND_MAGNITUDE
                                         else "Trending down" if r.trend_score <= -A.TREND_MAGNITUDE
                                         else "Holding steady")

    away_ident = _identity(tt, tg, a_id, game.away_logo)
    home_ident = _identity(tt, tg, h_id, game.home_logo)
    battlefields = _battlefields(tt, a_id, h_id, a_disp, h_disp)
    script = _game_script(tt, a_id, h_id, a_disp, h_disp, battlefields)
    away_snap = _snapshot(tt, tg, a_id, game.start_time, h_id)
    home_snap = _snapshot(tt, tg, h_id, game.start_time, a_id)
    shape = _shape_players(pf, trend_lookup, a_id, h_id)
    up, down = _player_trends(tf)
    away_tr = _team_trends(tg, a_id, tt.loc[a_id].team, game.away_logo)
    home_tr = _team_trends(tg, h_id, tt.loc[h_id].team, game.home_logo)
    opps = _opportunities(logs, game, tt, a_id, h_id)

    ar, hr = tt.loc[a_id], tt.loc[h_id]
    series = A.season_series(tg, a_id, h_id)
    hero = WNBAHero(
        away_team=game.away_name or a_disp, home_team=game.home_name or h_disp,
        away_logo=game.away_logo, home_logo=game.home_logo,
        away_record=f"{int(ar.wins)}-{int(ar.losses)}", home_record=f"{int(hr.wins)}-{int(hr.losses)}",
        tip_time=format_game_time(game.start_time), venue=game.venue,
        away_featured=_featured(pf, a_id), home_featured=_featured(pf, h_id),
        series=(f"Season series {series['away_wins']}-{series['home_wins']}" if series.get("played") else None),
        state=game.state, away_score=game.away_score, home_score=game.home_score,
        status_detail=game.status_detail)

    return WNBAGamePage(
        hero=hero, game_script=script, away_snapshot=away_snap, home_snapshot=home_snap,
        away_identity=away_ident, home_identity=home_ident, battlefields=battlefields,
        shape_players=shape, trending_up=up, trending_down=down,
        away_trends=away_tr, home_trends=home_tr, opportunities=opps,
        data_status=data_status, generated_at=datetime.now().isoformat(timespec="seconds"),
        as_of=as_of.isoformat())


def _match_team(tt, team_id, abbr, name):
    """Resolve a scheduled team to a team_id present in the logs."""
    def norm(v):
        return "".join(ch for ch in str(v or "").upper() if ch.isalnum())
    if team_id is not None and team_id in tt.index:
        return team_id
    targets = {norm(team_id), norm(abbr), norm(name)} - {""}
    for tid, row in tt.iterrows():
        if norm(tid) in targets or norm(row.team_abbr) in targets or norm(row.team) in targets:
            return tid
    return None
