"""The MLB postseason as a bracket: series, seeds, who has won what, and what is next.

Replaces the playoff *race* once there is a postseason to show. A race is a question
about the standings — who is in if the season ended today — and from the first Wild Card
game that question has an answer. What a reader wants in October is the bracket and the
state of each series, so that is what the playoff page shows from then on.

**Everything here is the source's facts, arranged.** The schedule of every series comes
from StatsAPI (``src/mlb_postseason``), placeholders and all; series wins are **counted
from final games by team id**, never parsed out of the source's "NYY leads 1-0" string;
seeds come from the final standings and are then checked against the bracket's own
pairings. Nothing projects a winner, and nothing reads odds.

**Why the seeds are checked, not trusted.** The pairings encode the seeding: a Wild Card
series is 3 v 6 or 4 v 5, hosted by the better seed, and seeds 1 and 2 go straight to the
Division Series. The standings feed has already been wrong once (it called a Wild Card a
division champion), so seeds that contradict the pairings are dropped for that league.
A bracket without seed numbers is incomplete; a bracket with the wrong ones is false.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from src.config import DB_PATH

ROUNDS = {  # game type -> (order, round name)
    "F": (1, "Wild Card Series"),
    "D": (2, "Division Series"),
    "L": (3, "Championship Series"),
    "W": (4, "World Series"),
}


@dataclass
class Side:
    team_id: str
    name: str                      # "New York Yankees", or the placeholder's own label
    short: str                     # "Yankees"
    abbr: str | None
    logo: str | None
    placeholder: bool
    seed: int | None = None
    wins: int = 0
    # For an unfilled slot: the series whose winner fills it, once known.
    feeder: "Series | None" = None

    @property
    def label(self) -> str:
        """How an unfilled slot is named: by where its occupant comes from."""
        if not self.placeholder:
            return self.short
        if self.feeder is not None:
            return f"{self.feeder.matchup_short} winner"
        return "To be decided"

    @property
    def compact_label(self) -> str:
        """The bracket's narrow cell: "NYY/BOS winner" rather than a name it truncates."""
        if self.placeholder and self.feeder is not None:
            abbrs = [x.abbr or x.short for x in (self.feeder.high, self.feeder.low)]
            return f"{'/'.join(abbrs)} winner"
        return self.label


@dataclass
class Game:
    game_id: str
    number: int | None
    start: str | None               # ISO instant from the source
    official_date: str | None
    time_tbd: bool
    if_necessary: bool
    state: str                      # pre | live | final
    status: str | None
    away_id: str
    home_id: str
    away_score: int | None
    home_score: int | None
    winner_id: str | None
    venue: str | None
    away_pitcher: str | None
    home_pitcher: str | None
    placeholder: bool               # either side still unknown


@dataclass
class Series:
    series_id: str
    game_type: str
    league: str | None             # "AL" | "NL" | None for the World Series
    label: str                     # the source's own name, "AL Wild Card 'A'"
    slug: str                      # "al-wild-card-a"
    best_of: int
    games: list[Game]
    high: Side                     # the better seed / the first game's host
    low: Side
    feeders: list["Series"] = field(default_factory=list)

    @property
    def order(self) -> int:
        return ROUNDS.get(self.game_type, (9, ""))[0]

    @property
    def round_name(self) -> str:
        name = ROUNDS.get(self.game_type, (9, "Postseason"))[1]
        return f"{self.league} {name}" if self.league else name

    @property
    def round_short(self) -> str:
        """"Wild Card", "ALDS", "NLCS", "World Series" — how the sport says it."""
        if self.game_type == "F":
            return f"{self.league} Wild Card"
        if self.game_type == "D":
            return f"{self.league}DS"
        if self.game_type == "L":
            return f"{self.league}CS"
        return "World Series"

    @property
    def wins_needed(self) -> int:
        return self.best_of // 2 + 1

    @property
    def known(self) -> bool:
        return not (self.high.placeholder or self.low.placeholder)

    @property
    def winner(self) -> Side | None:
        for side in (self.high, self.low):
            if side.wins >= self.wins_needed:
                return side
        return None

    @property
    def loser(self) -> Side | None:
        w = self.winner
        return None if w is None else (self.low if w is self.high else self.high)

    @property
    def state(self) -> str:
        """``decided`` | ``live`` (a game in progress) | ``underway`` | ``upcoming``."""
        if self.winner:
            return "decided"
        if any(g.state == "live" for g in self.games):
            return "live"
        if any(g.state == "final" for g in self.games):
            return "underway"
        return "upcoming"

    @property
    def matchup_short(self) -> str:
        return f"{self.high.label}–{self.low.label}"

    def side(self, team_id: str | None) -> Side | None:
        return next((s for s in (self.high, self.low) if s.team_id == str(team_id)), None)

    @property
    def summary(self) -> str:
        """"Yankees lead 1-0", "Series tied 1-1", "Yankees win 2-1", "Best of 5"."""
        return standing_line(self, self.high.wins, self.low.wins)

    @property
    def remaining_games(self) -> list[Game]:
        """Games still to be played. Once the series is decided the rest are not
        "if necessary" any more — they are not happening, and are not shown."""
        if self.winner:
            return []
        return [g for g in self.games if g.state != "final"]

    @property
    def next_game(self) -> Game | None:
        return next(iter(self.remaining_games), None)


def standing_line(series: Series, high_wins: int, low_wins: int) -> str:
    needed = series.wins_needed
    if high_wins == low_wins == 0:
        return f"Best of {series.best_of}"
    if high_wins >= needed or low_wins >= needed:
        side, a, b = ((series.high, high_wins, low_wins) if high_wins > low_wins
                      else (series.low, low_wins, high_wins))
        return f"{side.label} {_verb(side.label, 'win')} {a}-{b}"
    if high_wins == low_wins:
        return f"Series tied {high_wins}-{low_wins}"
    side, a, b = ((series.high, high_wins, low_wins) if high_wins > low_wins
                  else (series.low, low_wins, high_wins))
    return f"{side.label} {_verb(side.label, 'lead')} {a}-{b}"


def _verb(team: str, verb: str) -> str:
    # Club nicknames are plural ("Yankees lead", "Red Sox lead"); anything that is not
    # reads as one thing ("Astros–White Sox winner leads").
    plural = team.endswith("s") or team.endswith("Sox")
    return verb if plural and not team.endswith("winner") else f"{verb}s"


# --- parsing the snapshot -------------------------------------------------------------

_TBD_UTC_HOURS = range(6, 12)


def _time_tbd(game: dict) -> bool:
    """True when the source has not actually set a first pitch.

    StatsAPI flags some of these (``startTimeTBD``) and fills the rest with a sentinel
    in the small hours — 07:33 or 10:33 UTC, i.e. between 2 and 8 in the morning Eastern.
    No postseason game starts then, so a start in that band is read as "time not set"
    rather than printed as a 3:33 am first pitch.
    """
    if game.get("start_time_tbd"):
        return True
    try:
        start = datetime.fromisoformat(str(game.get("game_date")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    return start.hour in _TBD_UTC_HOURS


def _label(description: str | None) -> str:
    """"AL Wild Card 'A' Game 1" -> "AL Wild Card 'A'"; "NLCS Game 3" -> "NLCS"."""
    return re.sub(r"\s+Game\s+\d+\s*$", "", (description or "").strip())


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def _league(label: str) -> str | None:
    head = label[:2].upper()
    return head if head in ("AL", "NL") else None


def _side(game: dict, which: str) -> Side:
    return Side(
        team_id=str(game.get(f"{which}_id") or ""),
        name=game.get(which) or "",
        short=game.get(f"{which}_short") or game.get(which) or "",
        abbr=game.get(f"{which}_abbr"),
        logo=None if game.get(f"{which}_placeholder") else game.get(f"{which}_logo"),
        placeholder=bool(game.get(f"{which}_placeholder")),
    )


def _game(g: dict) -> Game:
    winner_id = None
    if g.get("state") == "final" and g.get("winner"):
        winner_id = str(g["away_id"] if g["winner"] == "away" else g["home_id"])
    return Game(
        game_id=str(g.get("game_pk")), number=g.get("series_game"),
        start=g.get("game_date"), official_date=g.get("official_date"),
        time_tbd=_time_tbd(g), if_necessary=bool(g.get("if_necessary")),
        state=g.get("state") or "pre", status=g.get("status_detail"),
        away_id=str(g.get("away_id") or ""), home_id=str(g.get("home_id") or ""),
        away_score=g.get("away_score"), home_score=g.get("home_score"),
        winner_id=winner_id, venue=g.get("venue"),
        away_pitcher=g.get("away_pitcher"), home_pitcher=g.get("home_pitcher"),
        placeholder=bool(g.get("away_placeholder") or g.get("home_placeholder")),
    )


def _series(entry: dict) -> Series | None:
    raw = sorted(entry.get("games") or [],
                 key=lambda g: (g.get("series_game") or 0, str(g.get("game_date"))))
    if not raw:
        return None
    first = raw[0]
    label = _label(first.get("game_description")) or str(entry.get("series_id"))
    # The first game's host is the better seed in every MLB round — home field goes to
    # the higher seed, in the World Series to the better record.
    high, low = _side(first, "home"), _side(first, "away")
    games = [_game(g) for g in raw]
    for g in games:
        if g.winner_id == high.team_id and not high.placeholder:
            high.wins += 1
        elif g.winner_id == low.team_id and not low.placeholder:
            low.wins += 1
    best_of = int(first.get("series_total") or len(raw))
    return Series(series_id=str(entry.get("series_id")),
                  game_type=str(entry.get("game_type") or first.get("phase") or ""),
                  league=_league(label), label=label, slug=_slug(label),
                  best_of=best_of, games=games, high=high, low=low)


def _link_feeders(series: list[Series]) -> None:
    """Which earlier series fills each slot, from the structure alone.

    A Division Series slot is filled from the Wild Card series that shares a club with it
    — either the club itself once it has advanced, or the placeholder the source names
    after the two clubs ("HOU/CWS"). A Championship Series takes its league's two
    Division Series; the World Series takes both pennants.
    """
    by_round: dict[int, list[Series]] = {}
    for s in series:
        by_round.setdefault(s.order, []).append(s)

    for s in series:
        prior = [p for p in by_round.get(s.order - 1, [])
                 if s.league is None or p.league == s.league]
        if s.game_type == "D":
            for side in (s.high, s.low):
                for p in prior:
                    ids = {p.high.team_id, p.low.team_id}
                    abbrs = {p.high.abbr, p.low.abbr}
                    named = set((side.abbr or "").split("/")) == abbrs
                    if side.team_id in ids or named:
                        s.feeders.append(p)
                        if side.placeholder:
                            side.feeder = p
        else:
            s.feeders = sorted(prior, key=_bracket_key)
            unfilled = [side for side in (s.high, s.low) if side.placeholder]
            # With both slots open, which feeder lands in which slot depends on seeds
            # not yet known, so neither is assigned — "ALDS winner" would be a guess
            # about which one. A single open slot has exactly one candidate.
            if len(unfilled) == 1:
                taken = {s.high.team_id, s.low.team_id}
                open_feeders = [p for p in prior
                                if not ({p.high.team_id, p.low.team_id} & taken)]
                if len(open_feeders) == 1:
                    unfilled[0].feeder = open_feeders[0]


def _apply_seeds(series: list[Series], seeds: dict[str, int]) -> set[str]:
    """Attach seeds, dropping any league whose seeds contradict its pairings.

    Returns the leagues whose seeds were dropped, so the page can say so.
    """
    dropped: set[str] = set()
    for league in ("AL", "NL"):
        rounds = [s for s in series if s.league == league]
        ok = bool(seeds)
        for s in rounds:
            hi, lo = seeds.get(s.high.team_id), seeds.get(s.low.team_id)
            if s.game_type == "F":
                ok &= hi is not None and lo is not None and hi + lo == 9 and hi < lo
            elif s.game_type == "D" and not s.high.placeholder:
                ok &= hi in (1, 2)
        if not ok:
            if seeds:
                dropped.add(league)
            continue
        for s in rounds:
            for side in (s.high, s.low):
                side.seed = seeds.get(side.team_id)
    # The World Series has no seeds of its own; each club carries its league seed.
    for s in series:
        if s.league is None:
            for side in (s.high, s.low):
                source_league = next((x.league for x in series
                                      if x.league and x.side(side.team_id)), None)
                if source_league and source_league not in dropped:
                    side.seed = seeds.get(side.team_id)
    return dropped


def _bracket_key(s: Series) -> tuple:
    """Top-to-bottom order within a round: the 1 seed's path first.

    Wild Card 4 v 5 feeds the 1 seed and 3 v 6 feeds the 2, so ordering both rounds by
    the best seed they lead to lines each Wild Card series up with the Division Series it
    feeds. Without seeds, the source's own letter ordering is the fallback.
    """
    def best(side: Side) -> int:
        return side.seed if side.seed else 99
    path = min(best(s.high), best(s.low))
    if s.game_type == "F" and s.high.seed:
        path = {4: 1, 3: 2}.get(s.high.seed, path)
    return (path, s.label)


@dataclass
class Bracket:
    season: int
    series: list[Series]
    head_to_head: dict[str, dict[str, int]]
    collected_at: str | None
    seeds_dropped: set[str]

    def round(self, game_type: str, league: str | None) -> list[Series]:
        found = [s for s in self.series if s.game_type == game_type and s.league == league]
        if game_type == "D":
            # Each Division Series sits beside the Wild Card series that feeds it.
            wc = self.round("F", league)
            found.sort(key=lambda s: next(
                (i for i, w in enumerate(wc) if w in s.feeders), 9))
        else:
            found.sort(key=_bracket_key)
        return found

    def by_slug(self, slug: str) -> Series | None:
        return next((s for s in self.series if s.slug == slug), None)

    def for_game(self, game_id: str | int) -> tuple[Series, Game] | tuple[None, None]:
        for s in self.series:
            for g in s.games:
                if g.game_id == str(game_id):
                    return s, g
        return None, None

    def meetings(self, a: str, b: str) -> dict[str, int] | None:
        return self.head_to_head.get("-".join(sorted((str(a), str(b)))))

    @property
    def champion(self) -> Side | None:
        ws = next((s for s in self.series if s.game_type == "W"), None)
        return ws.winner if ws else None

    @property
    def started(self) -> bool:
        return any(g.state != "pre" for s in self.series for g in s.games)

    def route(self, team_id: str, before: Series) -> list[tuple[Series, Side]]:
        """The series a club won on its way to ``before``: [(series, beaten side)]."""
        out = []
        for s in sorted(self.series, key=lambda x: x.order):
            if s.order >= before.order:
                continue
            if s.winner and s.winner.team_id == str(team_id):
                out.append((s, s.loser))
        return out


def build(payload: dict) -> Bracket:
    series = [s for s in (_series(e) for e in payload.get("series") or []) if s]
    dropped = _apply_seeds(series, {str(k): int(v)
                                    for k, v in (payload.get("seeds") or {}).items()})
    _link_feeders(series)
    slugs = [s.slug for s in series]
    if len(set(slugs)) != len(slugs):
        # Two series with one URL would silently publish one over the other.
        raise ValueError(f"Duplicate series slugs in the bracket: {slugs}")
    return Bracket(season=int(payload.get("season") or 0), series=series,
                   head_to_head=payload.get("head_to_head") or {},
                   collected_at=payload.get("collected_at"), seeds_dropped=dropped)


def load(as_of: date | None = None, db_path: Path = DB_PATH) -> Bracket | None:
    """The bracket to show on ``as_of``, or ``None`` when there is none to show.

    A snapshot from an earlier season is not this season's bracket — last October's
    must not be drawn beside this year's standings race — so a stale season is None.
    """
    from src import mlb_postseason

    today = as_of or date.today()
    payload = mlb_postseason.load(today, db_path)
    if not payload or int(payload.get("season") or 0) != today.year:
        return None
    bracket = build(payload)
    return bracket if bracket.series else None


def is_active(bracket: Bracket | None) -> bool:
    """Whether the playoff page should be the bracket rather than the race.

    From the moment the field is set — every Wild Card series has two real clubs — the
    race is over and the bracket is the page. Before that, a schedule full of
    placeholders is not a bracket anyone can read.
    """
    if bracket is None:
        return False
    wild_cards = [s for s in bracket.series if s.game_type == "F"]
    return bool(wild_cards) and all(s.known for s in wild_cards)


# --- one game in its series: for the slate card and the matchup page -----------------

@dataclass(frozen=True)
class GameInSeries:
    series: Series
    round_name: str                 # "AL Wild Card Series"
    game_line: str                  # "Game 2 of 3"
    standing: str                   # "Yankees lead 1-0" — going into this game
    seeds: dict[str, int | None]    # team_id -> seed
    stakes: str | None              # "Elimination game" | "Winner takes the series"
    href: str
    if_necessary: bool = False
    # False when an earlier game of the series is still to be decided, so ``standing``
    # is the series *now* rather than going into this game, and no stakes are claimed.
    settled: bool = True


def game_in_series(bracket: Bracket | None, game_id: str | int) -> GameInSeries | None:
    """Where one game sits in its series: going into it, or — once it is final — after it.

    The same convention as the source's ``seriesStatus``. A scheduled or live game reads
    as the series stood at first pitch, so a preview never contains a result; a final
    game reads as the series stands now, because "Yankees lead 1-0" beside a final that
    made it 2-0 is simply out of date. Counted from the bracket's own games by team id.
    """
    if bracket is None:
        return None
    series, game = bracket.for_game(game_id)
    if series is None or game is None:
        return None
    hi = lo = 0
    settled = True
    for g in series.games:
        if g is game and game.state != "final":
            break
        if g.state != "final":
            # Tomorrow's Game 3 behind tonight's Game 2: what it means depends on a
            # result nobody has yet. Say where the series stands, claim no stakes.
            settled = False
        if g.winner_id == series.high.team_id:
            hi += 1
        elif g.winner_id == series.low.team_id:
            lo += 1
        if g is game:
            break
    needed = series.wins_needed
    stakes = None
    if not settled or game.state == "final":
        pass
    elif hi == lo == needed - 1:
        stakes = "Winner takes the series"
    elif needed - 1 in (hi, lo) and max(hi, lo) < needed:
        stakes = "Elimination game"
    number = f"Game {game.number} of {series.best_of}" if game.number else f"Best of {series.best_of}"
    return GameInSeries(
        series=series, round_name=series.round_name, game_line=number,
        standing=standing_line(series, hi, lo),
        seeds={series.high.team_id: series.high.seed, series.low.team_id: series.low.seed},
        stakes=stakes, href=series_href(series),
        if_necessary=game.if_necessary and game.state == "pre", settled=settled)


def series_href(series: Series) -> str:
    return f"/playoffs/mlb/{series.slug}/"


def slate_series(games, as_of: date | None = None,
                 db_path: Path = DB_PATH) -> dict[str, GameInSeries]:
    """``{game_id: GameInSeries}`` for the MLB postseason games on a slate.

    Empty outside October, and empty rather than failing when no bracket was collected —
    the card then falls back to the source's own series line.
    """
    if not any(getattr(g, "league", None) == "MLB" and getattr(g, "is_postseason", False)
               for g in games):
        return {}
    bracket = load(as_of, db_path)
    out: dict[str, GameInSeries] = {}
    for game in games:
        if getattr(game, "league", None) != "MLB" or not game.is_postseason:
            continue
        info = game_in_series(bracket, game.game_id)
        if info:
            out[str(game.game_id)] = info
    return out
