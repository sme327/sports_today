"""The postseason prop desk: the evidence behind a player or starter line, arranged.

**What it is for.** A reader sees a line elsewhere — "Pivetta over 4.5 strikeouts",
"Tatis to record a hit" — opens the matchup page, and finds the evidence for it in a few
seconds. It is evidence, never a verdict: no odds are read, no score is computed, no row is
called strong or weak. (Decision log 2026-09-30.)

**Three slices that are never pooled.** The regular season, this postseason, and the
current series (this postseason's games against tonight's opponent — two clubs meet in at
most one series a year, so those are the same thing). The feed carries both phases in one
table; everything here splits on ``dataset`` first.

**Recent windows are the last 14 and 28 days *of the regular season*.** Anchoring them on
the slate date would fill them with playoff games within a week and pool the two phases by
the back door. They are labelled with their dates, so "L14 · Sep 14–27" says exactly what
it covers; the postseason slice holds everything after.

**Small samples are counts.** A postseason, a series, a season against one opponent and a
batter against one pitcher are all small. Every count carries its denominator, and a rate
is only ever printed beside it (``3/4``, never ``75%`` alone).

**What the evidence says matters, by market** (measured, see docs/engineering/METHOD.md and
the decision log): for a hit, plate appearances — i.e. lineup spot — beat recent form more
than two to one; batter strikeouts are carried by the opposing starter; starter strikeouts
are the site's best-measured signal, and in October the number of batters a starter faces
is half of it; hits allowed carried no information when measured; walks have no model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from services.data_access import is_postseason

WINDOWS = (28, 14)                 # days, widest first
STRIP_GAMES = 10                   # game-by-game strip length for a hitter
STRIP_STARTS = 6                   # for a starter
MIN_START_BF = 10                  # same bar as src/pitcher_opportunity: fewer is an opener
SMALL = 10                         # below this many games, show counts only

HITTER_MODES = ("hits", "tb", "bk")
STARTER_MODES = ("sk", "ha", "bb")
MODES = (("hits", "Hits"), ("tb", "Total bases"), ("bk", "Batter K"),
         ("sk", "Starter K"), ("ha", "Hits allowed"), ("bb", "Walks"))

# label, column, test — the thresholds a reader looks up after seeing a line elsewhere.
HITTER_THRESHOLDS = {
    "hits": (("1+ hit", "h", 1), ("2+ hits", "h", 2)),
    "tb": (("2+ TB", "tb", 2), ("3+ TB", "tb", 3), ("4+ TB", "tb", 4)),
    "bk": (("1+ K", "k", 1), ("2+ K", "k", 2)),
}
# (label, column, op, value): op ">=" clears at value or more, "<=" at value or fewer.
STARTER_THRESHOLDS = {
    "sk": (("4+ K", "k", ">=", 4), ("5+ K", "k", ">=", 5),
           ("6+ K", "k", ">=", 6), ("7+ K", "k", ">=", 7)),
    "ha": (("3 or fewer", "h", "<=", 3), ("4 or fewer", "h", "<=", 4),
           ("5 or fewer", "h", "<=", 5), ("6 or fewer", "h", "<=", 6)),
    "bb": (("1 or fewer", "bb", "<=", 1), ("2 or fewer", "bb", "<=", 2),
           ("3+", "bb", ">=", 3)),
}

NOTES = {
    "hits": "Lineup spot leads because it sets plate appearances, which predict a hit more "
            "than twice as well as recent hitting does.",
    "tb": "Total bases rides on the same chances as a hit, plus extra-base power. "
          "We do not model it; these are records.",
    "bk": "The opposing starter carries batter strikeouts more than the batter's own form, "
          "so his strikeout rate sits beside every row.",
    "sk": "Workload leads: a postseason hook can cut a starter's batters faced, and "
          "strikeouts need batters.",
    "ha": "Records only. When this market was measured, recent hits allowed carried no "
          "information beyond its base rate.",
    "bb": "Records only — the site has no walks model.",
}


# --- per-game frames -----------------------------------------------------------------

def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


def batter_games(pa: pd.DataFrame) -> pd.DataFrame:
    """One row per batter per game: chances, results, phase and batting slot.

    The slot is the order in which a team's first nine distinct batters came up, so it is
    a starter's lineup spot; a substitute's first appearance comes later and gets none.
    """
    if pa.empty:
        return pd.DataFrame()
    df = pa.assign(
        _post=is_postseason(pa).values,
        _h=_num(pa["is_hit"]), _tb=_num(pa["total_bases"]),
        _k=_num(pa["is_strikeout"]), _bb=_num(pa["is_walk"]),
        _ab=_num(pa["is_official_ab"]),
        _xbh=((_num(pa["is_hit"]) > 0) & (_num(pa["total_bases"]) >= 2)).astype(int),
    )
    df = df.sort_values(["game_id", "batting_team", "pa_number"], kind="stable")
    first = df.drop_duplicates(["game_id", "batting_team", "batter_id"])
    first = first.assign(slot=first.groupby(["game_id", "batting_team"]).cumcount() + 1)
    first.loc[first["slot"] > 9, "slot"] = 0
    games = df.groupby(["game_id", "batter_id"], sort=False).agg(
        game_date=("game_date", "first"), batter_name=("batter_name", "last"),
        batting_team=("batting_team", "first"), pitching_team=("pitching_team", "first"),
        post=("_post", "first"), pa=("pa_number", "size"), ab=("_ab", "sum"),
        h=("_h", "sum"), tb=("_tb", "sum"), k=("_k", "sum"), bb=("_bb", "sum"),
        xbh=("_xbh", "sum"),
    ).reset_index()
    games = games.merge(first[["game_id", "batter_id", "slot"]],
                        on=["game_id", "batter_id"], how="left")
    games["slot"] = games["slot"].fillna(0).astype(int)
    for col in ("pa", "ab", "h", "tb", "k", "bb", "xbh"):
        games[col] = games[col].astype(int)
    return games.sort_values("game_date").reset_index(drop=True)


def pitcher_appearances(pa: pd.DataFrame) -> pd.DataFrame:
    """One row per pitcher per game: workload, results, and whether it was a start.

    Pitches are the sum of each plate appearance's pitch count; innings are outs recorded
    while he was on the mound, over three. Both are close, not official: a pitcher pulled
    mid-count leaves that plate appearance to the reliever.
    """
    if pa.empty:
        return pd.DataFrame()
    inning = pd.to_numeric(pa["inning"].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
    df = pa.assign(
        _post=is_postseason(pa).values, _inn=inning,
        _pitches=_num(pa["pitch_count_pa"]), _outs=_num(pa["outs_on_play"]),
        _h=_num(pa["is_hit"]), _k=_num(pa["is_strikeout"]), _bb=_num(pa["is_walk"]),
    )
    apps = df.groupby(["game_id", "pitcher_id"], sort=False).agg(
        game_date=("game_date", "first"), pitcher_name=("pitcher_name", "last"),
        pitcher_hand=("pitcher_hand", "last"), team=("pitching_team", "first"),
        opp=("batting_team", "first"), post=("_post", "first"),
        first_inning=("_inn", "min"), bf=("pa_number", "size"),
        pitches=("_pitches", "sum"), outs=("_outs", "sum"),
        h=("_h", "sum"), k=("_k", "sum"), bb=("_bb", "sum"),
    ).reset_index()
    apps["start"] = (apps["first_inning"] == 1) & (apps["bf"] >= MIN_START_BF)
    for col in ("pitches", "outs", "h", "k", "bb", "bf"):
        apps[col] = apps[col].astype(int)
    return apps.sort_values("game_date").reset_index(drop=True)


# --- slices --------------------------------------------------------------------------

@dataclass(frozen=True)
class Count:
    """``hit`` of ``n`` — a count first, a rate only when the sample can carry one."""
    hit: int
    n: int

    @property
    def text(self) -> str:
        if not self.n:
            return "—"
        if self.n < SMALL:
            return f"{self.hit}/{self.n}"
        return f"{self.hit}/{self.n} · {round(100 * self.hit / self.n)}%"


@dataclass(frozen=True)
class HitterSlice:
    key: str                       # season | l28 | l14 | post | series | opp
    label: str
    span: str                      # what the slice covers, in words
    games: int
    pa: int
    ab: int
    h: int
    tb: int
    k: int
    bb: int
    xbh: int
    by_game: dict[str, tuple[int, ...]] = field(default_factory=dict)   # h/tb/k, oldest first

    @property
    def small(self) -> bool:
        return self.games < SMALL

    def clears(self, column: str, at_least: int) -> Count:
        values = self.by_game.get(column, ())
        return Count(sum(1 for v in values if v >= at_least), len(values))


def _hitter_slice(key: str, label: str, span: str, games: pd.DataFrame) -> HitterSlice:
    g = games.sort_values("game_date")
    return HitterSlice(
        key=key, label=label, span=span, games=len(g), pa=int(g["pa"].sum()),
        ab=int(g["ab"].sum()), h=int(g["h"].sum()), tb=int(g["tb"].sum()),
        k=int(g["k"].sum()), bb=int(g["bb"].sum()), xbh=int(g["xbh"].sum()),
        by_game={c: tuple(int(v) for v in g[c]) for c in ("h", "tb", "k")})


def _span(start: date, end: date) -> str:
    if start.month == end.month:
        return f"{start.strftime('%b %-d')}–{end.day}"
    return f"{start.strftime('%b %-d')}–{end.strftime('%b %-d')}"


@dataclass(frozen=True)
class Hitter:
    pid: str
    name: str
    slot: int | None
    hand: str | None               # L | R | S
    confirmed: bool
    slices: dict[str, HitterSlice]
    pa_per_game: float | None      # regular season, games he started
    slot_pa: float | None          # league PA/game from tonight's slot, for scale
    vs_hand: Count | None          # regular-season strikeouts per PA vs tonight's starter's hand
    bvp: HitterSlice | None        # every 2026 PA against tonight's starter
    strip: dict[str, tuple[int, ...]] = field(default_factory=dict)   # last games, any phase
    strip_post: tuple[bool, ...] = ()                                  # which of those were playoff games

    @property
    def bats(self) -> str:
        return {"L": "L", "R": "R", "S": "S"}.get(self.hand or "", "—")

    @property
    def bvp_line(self) -> str:
        if self.bvp is None or not self.bvp.pa:
            return "No meetings this season"
        b = self.bvp
        bits = [f"{b.h}-for-{b.ab}"]
        if b.xbh:
            bits.append(f"{b.xbh} XBH")
        bits += [f"{b.k} K"]
        if b.bb:
            bits.append(f"{b.bb} BB")
        return ", ".join(bits) + f" in {b.pa} PA"


def _slot_pa(games: pd.DataFrame) -> dict[int, float]:
    """League plate appearances per game by lineup spot, regular season, starters only."""
    reg = games[(~games["post"]) & (games["slot"] > 0)]
    if reg.empty:
        return {}
    return {int(s): round(float(v), 2) for s, v in reg.groupby("slot")["pa"].mean().items()}


# --- starters ------------------------------------------------------------------------

@dataclass(frozen=True)
class Outing:
    day: str                        # "Sep 24"
    opp: str
    pitches: int
    bf: int
    outs: int
    k: int
    h: int
    bb: int
    start: bool

    @property
    def ip(self) -> str:
        """Baseball's notation: 5.2 is five and two-thirds."""
        return f"{self.outs // 3}.{self.outs % 3}"


@dataclass(frozen=True)
class Starter:
    pid: str
    name: str
    hand: str | None
    team: str
    opp: str
    starts: int                                   # regular season
    avg: dict[str, float]                         # per regular-season start
    recent: tuple[Outing, ...]                    # last regular-season starts, oldest first
    post: tuple[Outing, ...]                      # this postseason, starts and relief
    vs_opp: tuple[Outing, ...]                    # regular-season starts against tonight's club
    thresholds: dict[str, tuple[tuple[str, Count, Count, Count], ...]]   # label, season, recent, post
    lineup: dict[str, Count] = field(default_factory=dict)   # opposing nine vs his hand
    lineup_note: str = ""

    @property
    def throws(self) -> str:
        return {"L": "LHP", "R": "RHP"}.get(self.hand or "", "SP")


def _outing(row) -> Outing:
    return Outing(day=pd.Timestamp(row["game_date"]).strftime("%b %-d"),
                  opp=str(row["opp"]), pitches=int(row["pitches"]), bf=int(row["bf"]),
                  outs=int(row["outs"]), k=int(row["k"]), h=int(row["h"]), bb=int(row["bb"]),
                  start=bool(row["start"]))


def _clear(values, op: str, value: int) -> Count:
    values = list(values)
    hit = sum(1 for v in values if (v >= value if op == ">=" else v <= value))
    return Count(hit, len(values))


def build_starter(apps: pd.DataFrame, pid: str | None, opp: str) -> Starter | None:
    if not pid:
        return None
    mine = apps[apps["pitcher_id"].astype(str) == str(pid)]
    if mine.empty:
        return None
    reg = mine[(~mine["post"]) & mine["start"]]
    post = mine[mine["post"]]
    recent = reg.tail(STRIP_STARTS)
    n = max(len(reg), 1)
    avg = {c: round(float(reg[c].sum()) / n, 1) for c in ("pitches", "bf", "k", "h", "bb")}
    avg["outs"] = float(reg["outs"].sum()) / n
    thresholds = {}
    for mode, rows in STARTER_THRESHOLDS.items():
        thresholds[mode] = tuple(
            (label, _clear(reg[col], op, v), _clear(recent[col], op, v),
             _clear(post[post["start"]][col], op, v))
            for label, col, op, v in rows)
    last = mine.iloc[-1]
    return Starter(
        pid=str(pid), name=str(last["pitcher_name"]),
        hand=str(last["pitcher_hand"]) if pd.notna(last["pitcher_hand"]) else None,
        team=str(last["team"]), opp=opp, starts=len(reg), avg=avg,
        recent=tuple(_outing(r) for _, r in recent.iterrows()),
        post=tuple(_outing(r) for _, r in post.iterrows()),
        vs_opp=tuple(_outing(r) for _, r in reg[reg["opp"] == opp].iterrows()),
        thresholds=thresholds)


# --- the lineup ----------------------------------------------------------------------

def _last_game_order(games: pd.DataFrame, team: str) -> tuple[tuple[str, str], ...]:
    """The team's most recent batting order in the feed, for when tonight's is not posted."""
    mine = games[(games["batting_team"] == team) & (games["slot"] > 0)]
    if mine.empty:
        return ()
    last = mine[mine["game_id"] == mine.sort_values("game_date")["game_id"].iloc[-1]]
    last = last.sort_values("slot")
    return tuple((str(r["batter_id"]), str(r["batter_name"])) for _, r in last.iterrows())


def _hand(pa: pd.DataFrame, pid: str) -> str | None:
    hands = pa.loc[pa["batter_id"] == pid, "batter_hand"].dropna()
    return str(hands.mode().iloc[0]) if not hands.empty else None


def build_hitter(pa: pd.DataFrame, games: pd.DataFrame, pid: str, name: str,
                 slot: int | None, confirmed: bool, opp: str, starter: Starter | None,
                 reg_end: date | None, slot_pa: dict[int, float]) -> Hitter:
    mine = games[games["batter_id"] == pid]
    reg, post = mine[~mine["post"]], mine[mine["post"]]
    slices: dict[str, HitterSlice] = {
        "season": _hitter_slice("season", "Regular season", "all of it", reg)}
    if reg_end is not None:
        for days in WINDOWS:
            start = reg_end - timedelta(days=days - 1)
            window = reg[reg["game_date"].dt.date >= start]
            slices[f"l{days}"] = _hitter_slice(f"l{days}", f"L{days}", _span(start, reg_end),
                                               window)
    slices["post"] = _hitter_slice("post", "Postseason", "this October", post)
    slices["series"] = _hitter_slice("series", "This series", f"vs {opp}",
                                     post[post["pitching_team"] == opp])
    slices["opp"] = _hitter_slice("opp", f"vs {opp}", "regular season",
                                  reg[reg["pitching_team"] == opp])

    started = reg[reg["slot"] > 0]
    pa_per_game = round(float(started["pa"].mean()), 2) if not started.empty else None

    vs_hand = bvp = None
    if starter is not None:
        his = pa[pa["batter_id"] == pid]
        if starter.hand:
            side = his[(~is_postseason(his)) & (his["pitcher_hand"] == starter.hand)]
            vs_hand = Count(int(_num(side["is_strikeout"]).sum()), len(side))
        faced = his[his["pitcher_id"].astype(str) == starter.pid]
        if not faced.empty:
            bvp = _hitter_slice("bvp", f"vs {starter.name}", "2026, both phases",
                                batter_games(faced))
    last = mine.tail(STRIP_GAMES)
    return Hitter(pid=pid, name=name, slot=slot, hand=_hand(pa, pid), confirmed=confirmed,
                  slices=slices, pa_per_game=pa_per_game,
                  slot_pa=slot_pa.get(slot) if slot else None, vs_hand=vs_hand, bvp=bvp,
                  strip={c: tuple(int(v) for v in last[c]) for c in ("h", "tb", "k", "bb")},
                  strip_post=tuple(bool(v) for v in last["post"]))


@dataclass(frozen=True)
class Side:
    team: str                      # full name, the feed's own
    short: str
    confirmed: bool
    source: str                    # how the order was obtained, in words
    hitters: tuple[Hitter, ...]
    starter: Starter | None        # this side's starter (who faces the *other* lineup)


@dataclass(frozen=True)
class PropDesk:
    away: Side
    home: Side
    data_through: date | None
    reg_end: date | None
    modes: tuple[tuple[str, str], ...] = MODES
    notes: dict[str, str] = field(default_factory=lambda: dict(NOTES))

    @property
    def starters(self) -> tuple[Starter, ...]:
        return tuple(s for s in (self.away.starter, self.home.starter) if s)


def _lineup_profile(starter: Starter | None, hitters: tuple[Hitter, ...], pa: pd.DataFrame
                    ) -> tuple[dict[str, Count], str]:
    """The opposing nine against this starter's hand: strikeouts, walks and hits per PA,
    pooled over their regular-season plate appearances. Raw counts, so the reader can see
    it is several thousand PA and not a guess."""
    if starter is None or not hitters or not starter.hand:
        return {}, ""
    ids = {h.pid for h in hitters}
    rows = pa[(pa["batter_id"].isin(ids)) & (~is_postseason(pa))
              & (pa["pitcher_hand"] == starter.hand)]
    n = len(rows)
    if not n:
        return {}, ""
    profile = {"k": Count(int(_num(rows["is_strikeout"]).sum()), n),
               "bb": Count(int(_num(rows["is_walk"]).sum()), n),
               "h": Count(int(_num(rows["is_hit"]).sum()), n)}
    hand = "LHP" if starter.hand == "L" else "RHP"
    return profile, f"{len(ids)} hitters vs {hand}, regular season"


def build(pa: pd.DataFrame, *, away_team: str, home_team: str, away_short: str,
          home_short: str, away_pid: str | None, home_pid: str | None,
          lineups=None) -> PropDesk | None:
    """The whole desk for one game. ``pa`` is every plate appearance before the slate
    date, both phases; this function does the splitting."""
    if pa.empty:
        return None
    # Ids as strings once, up front, so every per-player filter below is a plain compare.
    pa = pa.assign(batter_id=pa["batter_id"].astype(str))
    games = batter_games(pa)
    apps = pitcher_appearances(pa)
    reg_dates = games.loc[~games["post"], "game_date"]
    reg_end = reg_dates.max().date() if not reg_dates.empty else None
    data_through = games["game_date"].max().date() if not games.empty else None
    slot_pa = _slot_pa(games)

    away_sp = build_starter(apps, away_pid, home_team)
    home_sp = build_starter(apps, home_pid, away_team)

    def side(team: str, short: str, facing: Starter | None, own: Starter | None,
             opp: str) -> Side:
        posted = bool(lineups and lineups.is_posted(team) and lineups.order.get(team))
        if posted:
            order = tuple((str(pid), name) for pid, name in lineups.order[team])
            source = "Confirmed lineup"
        else:
            order = _last_game_order(games, team)
            source = "Not posted yet — showing the last game's order, not tonight's"
        hitters = tuple(
            build_hitter(pa, games, pid, name, i, posted, opp, facing, reg_end, slot_pa)
            for i, (pid, name) in enumerate(order, 1))
        return Side(team=team, short=short, confirmed=posted, source=source,
                    hitters=hitters, starter=own)

    away = side(away_team, away_short, home_sp, away_sp, home_team)
    home = side(home_team, home_short, away_sp, home_sp, away_team)

    # Each starter's opposing-lineup profile is built from the *other* side's nine.
    def with_profile(sp: Starter | None, opposing: Side) -> Starter | None:
        if sp is None:
            return None
        profile, note = _lineup_profile(sp, opposing.hitters, pa)
        return Starter(**{**sp.__dict__, "lineup": profile, "lineup_note": note})

    away = Side(**{**away.__dict__, "starter": with_profile(away.starter, home)})
    home = Side(**{**home.__dict__, "starter": with_profile(home.starter, away)})
    return PropDesk(away=away, home=home, data_through=data_through, reg_end=reg_end)
