"""Everything you need to write one NFL game's note, in one command.

    python -m scripts.nfl_dossier                 # this week's games and what each has
    python -m scripts.nfl_dossier 401872925       # the dossier for one game
    python -m scripts.nfl_dossier 401872925 --line "Ja'Marr Chase" receptions 7.5 105 -135

**Why a script and not a habit.** Writing a note by hand means gathering the same six
things every time: the engine's read, the measured defence ratings, the official injury
report, who actually moved between rosters, each side's usage, and whether someone else is
already writing this game. On 2026-09-13 the roster comparison was done ad hoc with exact
name matching and got four players wrong, two of which had editorial built on them. A
documented rule nobody can run is a rule that gets skipped under time pressure, so the
**name check runs as part of the dossier** rather than living in a README.

Nothing here writes a note: it prints facts. The editorial judgement is yours, and the
method for turning a posted line into a call is in `content/nfl/README.md`.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys

import pandas as pd
import requests

from services import nfl_matchup as M
from services.nfl_game_notes import NOTES_DIR, load_notes
from services.nfl_game_page import build_nfl_pregame_page
from services.nfl_repository import load_player_games
from src.config import DB_PATH
from src.espn_http import espn_get
from src.odds import edge, implied_probability, no_vig

ROSTER = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{tid}/roster"
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary"
_HEADERS = {"Accept": "application/json"}
_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?")


def norm(name: str) -> str:
    """A name with suffixes and punctuation removed, for comparing ESPN against the feed.

    ESPN says "James Cook III" and "Travis Etienne Jr." where the vendor feed says "James
    Cook" and "Travis Etienne". Comparing raw strings reports both as departed. This does
    not fix nicknames — ESPN's "Kenny Gainwell" against the feed's "Kenneth" still slips
    through — so the output flags near-misses for a human to read.
    """
    n = _SUFFIX.sub("", str(name).lower().replace(".", "").replace("'", ""))
    return re.sub(r"\s+", " ", n).strip()


def _get(url: str, **params):
    return espn_get(requests.get, url, params=params or None, headers=_HEADERS, timeout=25).json()


def _games(conn, week: int | None):
    sql = ("select game_id, start_time, venue, away_id, away_name, home_id, home_name "
           "from nfl_schedule where season = 2026")
    args: list = []
    if week:
        sql += " and week = ?"
        args.append(week)
    return conn.execute(sql + " order by start_time", args).fetchall()


def overview(conn, week: int | None) -> None:
    led = {r[0]: (r[1], r[2]) for r in conn.execute(
        "select game_id, count(*), sum(direction <> 'pass') from nfl_lean_ledger group by 1")}
    print(f"{'event':12s} {'kickoff (UTC)':18s} {'game':34s} note  board")
    for gid, start, _v, _ai, away, _hi, home in _games(conn, week):
        n, calls = led.get(gid, (0, 0))
        note = "yes" if (NOTES_DIR / f"{gid}.toml").is_file() else "—"
        board = f"{calls} of {n}" if n else "—"
        print(f"{gid:12s} {start[:16]:18s} {away.split()[-1] + ' at ' + home.split()[-1]:34s} "
              f"{note:5s} {board}")


def _usage(pg: pd.DataFrame, team: str, season: int) -> pd.DataFrame:
    d = pg[(pg.team == team) & (pg.season == season)]
    if d.empty:
        return d
    g = (d.assign(vol=d.passing_att + d.rushing_att + d.receiving_tar)
           .groupby(["player", "position"])
           .agg(g=("game_id", "nunique"), att=("passing_att", "mean"), car=("rushing_att", "mean"),
                ry=("rushing_yds", "mean"), tgt=("receiving_tar", "mean"),
                rec=("receiving_rec", "mean"), recy=("receiving_yds", "mean"),
                vol=("vol", "mean")).reset_index())
    return g[g.vol >= 2].sort_values("vol", ascending=False)


def dossier(conn, gid: str, lines: list[tuple]) -> int:
    row = conn.execute(
        "select start_time, venue, away_id, away_name, home_id, home_name from nfl_schedule "
        "where season = 2026 and game_id = ?", (gid,)).fetchone()
    if row is None:
        print(f"No 2026 game {gid} in nfl_schedule.", file=sys.stderr)
        return 1
    start, venue, away_id, away, home_id, home = row
    kickoff = start[:10]
    print(f"=== {away} at {home} — {start} — {venue} — event {gid}\n")

    # Somebody else may already be writing this game (two sessions did on 2026-09-13).
    path = NOTES_DIR / f"{gid}.toml"
    if path.is_file():
        log = subprocess.run(["git", "log", "-1", "--format=%h %ad %an %s", "--date=short",
                              "--", str(path)], capture_output=True, text=True).stdout.strip()
        notes = load_notes(gid)
        board = notes.in_section("props") if notes else ()
        print(f"NOTE EXISTS — last commit: {log or '(uncommitted)'}")
        print(f"  board: {len([l for l in board if l.direction != 'pass'])} calls of {len(board)}"
              f" · availability {len(notes.availability)} · falsifiers {len(notes.falsifiers)}\n")

    pg = load_player_games()
    before = pg[pg["game_date"].astype("string") < kickoff]
    season = 2026 if not before[before.season == 2026].empty else 2025
    print(f"--- BASELINE SEASON: {season}"
          f"{'  (2026 games exist — cite those, not 2025)' if season == 2026 else '  (no 2026 games yet)'}\n")

    page = build_nfl_pregame_page(away, home, kickoff, "Week", 2026)
    if page:
        print(f"--- ENGINE  records {page.hero.away_record} | {page.hero.home_record}")
        for t in page.thesis:
            print(f"    {t}")
        for r in page.identity:
            print(f"    {r.label:24s} {r.away_value:>7} {str(r.away_pct):>4} | "
                  f"{str(r.home_pct):>4} {r.home_value:>7}  ({r.better})")
        for b in page.battlefields:
            print(f"    {b.label}: {b.attack} ({b.attack_pct}) -> {b.defense} ({b.defense_pct}) {b.edge}")
        if page.away_form:
            print(f"    form {away.split()[-1]} {page.away_form.results} | "
                  f"{home.split()[-1]} {page.home_form.results if page.home_form else '-'}")
        for s in page.away_spotlights + page.home_spotlights:
            mx = f" · {s.matchup.direction} {s.matchup.swing:+.0f}" if s.matchup else ""
            print(f"    SPOT {s.player} ({s.position}) {s.market} · {s.support}{mx}")

    print("\n--- MEASURED DEFENCE (own-baseline; negative = suppresses, soft is measured to do nothing)")
    ratings = M.ratings_for(before, kickoff)
    for stat, series in ratings.items():
        s = series.sort_values()
        for t in (away, home):
            if t in s.index:
                v = float(s.loc[t])
                rank = int((s < v).sum()) + 1
                tag = "TOUGH" if rank <= 8 else ("soft (no lift)" if rank >= 25 else "average")
                print(f"    {t.split()[-1]:12s} {stat:13s} {v:+6.1f}  rank {rank}/{len(s)}  {tag}")

    print("\n--- INJURY REPORT (ESPN, live)")
    try:
        summ = _get(SUMMARY, event=gid)
        for blk in summ.get("injuries", []):
            for p in blk.get("injuries", []):
                det = p.get("details") or {}
                bits = " ".join(x for x in (det.get("type"), det.get("detail"))
                                if x and x != "Not Specified")
                print(f"    {blk['team']['displayName'].split()[-1]:12s} "
                      f"{p['athlete']['displayName']:24s} "
                      f"{p['athlete'].get('position', {}).get('abbreviation', ''):4s} "
                      f"{p.get('status', ''):18s} {bits}")
    except Exception as exc:                            # noqa: BLE001
        print(f"    fetch failed: {exc}")

    print("\n--- ROSTER CHECK (suffix-insensitive; this is the check that caught four errors)")
    last = pg.sort_values("game_date").groupby("player").tail(1).set_index("player")["team"].to_dict()
    vol = (pg.assign(v=pg.passing_att + pg.rushing_att + pg.receiving_tar)
             .groupby("player").v.mean().to_dict())
    for team, tid in ((away, away_id), (home, home_id)):
        try:
            r = _get(ROSTER.format(tid=tid))
        except Exception as exc:                        # noqa: BLE001
            print(f"    {team}: roster fetch failed: {exc}")
            continue
        on = {}
        for grp in r.get("athletes", []):
            for a in grp.get("items", []):
                on[norm(a["displayName"])] = (a["displayName"], grp.get("position"))
        feed = {p for p, t in last.items() if t == team and (vol.get(p) or 0) >= 4}
        gone = sorted(p for p in feed if norm(p) not in on)
        arrived = sorted(
            (on[norm(p)][0], p, last[p].split()[-1], round(vol[p], 1))
            for p in last
            if last[p] != team and norm(p) in on and (vol.get(p) or 0) >= 4
            and on[norm(p)][1] not in ("practiceSquad",))
        renamed = sorted((p, on[norm(p)][0]) for p in feed
                         if norm(p) in on and on[norm(p)][0] != p)
        coach = [c.get("firstName", "") + " " + c.get("lastName", "") for c in r.get("coach", [])]
        print(f"    {team} · coach {', '.join(coach) or '?'}")
        print(f"      departed ({len(gone)}): " + ("; ".join(f"{p} {vol[p]:.1f}" for p in gone) or "—"))
        print(f"      arrived  ({len(arrived)}): "
              + ("; ".join(f"{e} (feed '{f}', from {old}, {v})" for e, f, old, v in arrived) or "—"))
        if renamed:
            print("      NAME MISMATCH, same player: "
                  + "; ".join(f"feed '{f}' = ESPN '{e}'" for f, e in renamed))

    for team in (away, home):
        u = _usage(pg, team, season)
        if not u.empty:
            print(f"\n--- USAGE {team} ({season})")
            print("    " + u.head(12).to_string(index=False,
                  float_format=lambda x: f"{x:.1f}").replace("\n", "\n    "))

    if lines:
        print("\n--- POSTED LINES vs THE RECORD (see content/nfl/README.md for the method)")
        print(f"    {'player':24s} {'market':16s} {'line':>6s} {'cleared':>16s} {'price':>12s}"
              f" {'break-even':>11s} {'gap':>7s}")
        for player, stat, ln, over_price, under_price in lines:
            # The baseline season only, never pooled across seasons: a 2023 game does not
            # describe this player's role, and pooling quietly triples the sample.
            d = pg[(pg.player == player) & (pg.season == season)
                   & (pg["game_date"].astype("string") < kickoff)].sort_values("game_date")
            if stat not in d.columns or d.empty:
                print(f"    {player:24s} {stat:16s} {ln:>6} {'NO ' + str(season) + ' DATA':>16s}")
                continue
            v = pd.to_numeric(d[stat], errors="coerce").dropna()
            rate = float((v > ln).mean())
            last6 = v.tail(6)
            fair_over, _ = no_vig(over_price, under_price)
            print(f"    {player:24s} {stat:16s} {ln:>6} "
                  f"{f'{rate:.0%} ({int((v > ln).sum())}/{len(v)})':>16s} "
                  f"{f'{over_price:+d}/{under_price:+d}':>12s} "
                  f"{implied_probability(over_price):>10.0%} "
                  f"{edge(rate, over_price):>+7.0%}  no-vig {fair_over:.0%}"
                  f"  last6 {(last6 > ln).mean():.0%} avg {last6.mean():.1f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game_id", nargs="?", help="ESPN event id; omit to list this season's games")
    ap.add_argument("--week", type=int, help="with no game_id, limit the listing to one week")
    ap.add_argument("--line", nargs=5, action="append", metavar=("PLAYER", "STAT", "LINE", "OVER", "UNDER"),
                    help="a posted line to score against the record; repeatable")
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args(argv)
    lines = [(p, s, float(l), int(o), int(u)) for p, s, l, o, u in (args.line or [])]
    with sqlite3.connect(f"file:{args.db}?mode=ro", uri=True) as conn:
        if not args.game_id:
            overview(conn, args.week)
            return 0
        return dossier(conn, args.game_id, lines)


if __name__ == "__main__":
    sys.exit(main())
