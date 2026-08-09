"""Editorial signals — curation for leagues that have no player props.

MLB and WNBA earn their place on the slate through player opportunities. Football,
hockey and basketball schedules currently arrive with none, so without something else
they are just a list of fixtures. These signals give a team-level answer to "which of
these is worth my attention, and why" from the only material the schedule honestly
provides: each side's record, a poll rank where the sport has one, whether it is a
conference game, and where the game sits in the season.

Deliberately **not** used, and the reasons:

- **Betting odds.** ESPN serves a spread on every event and it would be the easiest
  possible signal. The product says no — the Vision lists odds among the things fans
  are already drowning in and states three times that this is not a sportsbook, and
  the prop scorers already refuse them ("we ingest no odds"). Reversing that is a
  product decision, not an implementation shortcut.
- **Injuries, weather, travel.** Not in this feed. Absent, not approximated.
- **Playoff leverage.** Real leverage needs standings and elimination maths, which
  needs the series/bracket model. A guess dressed as leverage would be worse than
  saying nothing, so this module says nothing.

Every signal carries the evidence it was computed from, and its caveats are returned
alongside — never buried — because a record gap is a description of the past, not a
forecast. Nothing here is a probability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from domain.models import SlateGame

# A record needs some substance before it means anything. Four games is the same bar
# the prop scorers use; below it a team is "2-0" on noise.
MIN_GAMES = 4

# Distinct teams a league must field on a slate before its spread is worth measuring.
# Eight is four games — below that the "league" is a handful of teams and its mean
# says more about who happens to be playing than about the competition.
MIN_TEAMS_FOR_NORM = 8

_STRONG = 0.650        # win pct that counts as a good team
_WINNING = 0.500       # above water — the broad middle most pro teams live in
_CLOSE = 0.100         # win-pct gap within which two teams are evenly matched
_WIDE = 0.300          # win-pct gap that makes a game lopsided on paper
_RANKED_TOP = 10       # "top-10" for poll-rank purposes

_RECORD_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)(?:\s*-\s*(\d+))?\s*$")
# College short names arrive pre-prefixed with their poll rank ("#7 BYU"); signal
# text adds its own, so strip it rather than printing "#7 #7 BYU".
_RANK_PREFIX_RE = re.compile(r"^\s*#\d+\s+")


@dataclass(frozen=True)
class Standing:
    """One team's record going into a game. ``win_pct`` is None until the sample is
    real, so callers cannot accidentally treat 0-0 as a .000 team."""

    record: str | None
    wins: int = 0
    losses: int = 0
    ties: int = 0
    rank: int | None = None

    @property
    def games(self) -> int:
        return self.wins + self.losses + self.ties

    @property
    def win_pct(self) -> float | None:
        if self.games < MIN_GAMES:
            return None
        return (self.wins + 0.5 * self.ties) / self.games

    @property
    def is_ranked(self) -> bool:
        return self.rank is not None


@dataclass(frozen=True)
class LeagueNorm:
    """How a league's records are spread, so a team can be judged against its own
    competition rather than an absolute number.

    A .620 team is dominant in baseball and mediocre in football: MLB's season pulls
    everyone toward .500 while a 17-game NFL season lets teams reach .900. Comparing
    raw win percentage across sports therefore measures the sport, not the team.
    """

    league: str
    mean: float
    sd: float
    teams: int

    @property
    def usable(self) -> bool:
        """Enough distinct teams, and enough spread, for the shape to mean anything.
        A two-team slate says nothing about its league."""
        return self.teams >= MIN_TEAMS_FOR_NORM and self.sd >= 0.01

    def strength(self, win_pct: float | None) -> float | None:
        """A team's standing within its own league on a 0-1 scale.

        Two standard deviations either side of the league mean spans the scale, which
        keeps a dominant baseball team and a dominant football team near the same
        number instead of an artefact of their sport's schedule length.
        """
        if win_pct is None or not self.usable:
            return None
        z = (win_pct - self.mean) / self.sd
        return round(min(max((z + 2.0) / 4.0, 0.0), 1.0), 4)


@dataclass(frozen=True)
class Signal:
    """One editorial observation about a game, with its reasoning attached."""

    kind: str                      # machine key, e.g. "marquee"
    label: str                     # short chip text, e.g. "Marquee matchup"
    detail: str                    # one plain sentence
    evidence: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()  # shown with equal prominence, never hidden


@dataclass(frozen=True)
class GameInterest:
    """Why a game is (or is not) worth attention. ``score`` ranks games against each
    other on a given slate — it is an attention ranking, **not** a win probability and
    not comparable to a prop's Opportunity Score. ``components`` exposes every part
    that produced it so the number is always inspectable."""

    score: int
    components: dict[str, float]
    signals: tuple[Signal, ...]
    caveats: tuple[str, ...]

    @property
    def headline(self) -> Signal | None:
        return self.signals[0] if self.signals else None


def parse_record(record: str | None, rank: int | None = None) -> Standing:
    """Parse a source record summary ("8-3", "9-0-1") into a Standing.

    Unparseable or missing input yields an empty Standing rather than raising — a
    league that does not publish records simply produces no signals.
    """
    if not record:
        return Standing(record=None, rank=rank)
    m = _RECORD_RE.match(str(record))
    if not m:
        return Standing(record=str(record), rank=rank)
    wins, losses, ties = (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
    return Standing(record=str(record), wins=wins, losses=losses, ties=ties, rank=rank)


def standings(game: SlateGame) -> tuple[Standing, Standing]:
    """(away, home) standings as the source reported them."""
    return (parse_record(game.away_record, game.away_rank),
            parse_record(game.home_record, game.home_rank))


def _side_name(game: SlateGame, side: str) -> str:
    value = (game.away_short or game.away_name if side == "away"
             else game.home_short or game.home_name)
    return _RANK_PREFIX_RE.sub("", value) if value else side.title()


def _rec(name: str, s: Standing) -> str:
    return f"{name} {s.record}" if s.record else name


def _quality_signals(game: SlateGame, away: Standing, home: Standing) -> list[Signal]:
    """Signals that need both records to be real."""
    ap, hp = away.win_pct, home.win_pct
    if ap is None or hp is None:
        return []
    a_name, h_name = _side_name(game, "away"), _side_name(game, "home")
    evidence = (_rec(a_name, away), _rec(h_name, home))
    gap = abs(ap - hp)
    out: list[Signal] = []

    if ap >= _STRONG and hp >= _STRONG:
        out.append(Signal(
            "marquee", "Marquee matchup",
            f"Two winning sides: {a_name} and {h_name} both above .650.",
            evidence))
    elif min(ap, hp) >= _WINNING:
        # The broad middle, where most professional games live. Without this a
        # 6-5 vs 8-3 game scored well and explained nothing.
        out.append(Signal(
            "solid", "Winning records",
            f"Both {a_name} and {h_name} come in above .500.",
            evidence))
    if gap <= _CLOSE and min(ap, hp) >= 0.400:
        out.append(Signal(
            "even", "Evenly matched",
            f"{a_name} and {h_name} have nearly identical records.",
            evidence))
    if gap >= _WIDE:
        stronger, weaker = ((a_name, h_name) if ap > hp else (h_name, a_name))
        weaker_is_home = (hp < ap)
        # An upset is only a story when the favourite is actually good. Without this
        # a 5-6 side hosting a 8-3 side read as an "upset setup", which fired on 10
        # of 45 college games and cheapened the label.
        favourite_is_strong = max(ap, hp) >= _STRONG
        if favourite_is_strong and (weaker_is_home or game.neutral_site):
            where = "at home" if weaker_is_home and not game.neutral_site else "on a neutral field"
            out.append(Signal(
                "upset_setup", "Upset setup",
                f"{stronger} are much stronger on record, but {weaker} are {where}.",
                evidence,
                caveats=("A record gap describes the season so far, not tonight — "
                         "no injury, rest or matchup context is included.",)))
        else:
            out.append(Signal(
                "mismatch", "Lopsided on paper",
                f"{stronger} come in far ahead of {weaker} on record.",
                evidence,
                caveats=("Record gap only; nothing here accounts for injuries or "
                         "how the teams match up.",)))
    if not out:
        # Records are known but nothing above fired. Say something plain rather than
        # leaving a scored game with no explanation attached to it.
        if max(ap, hp) < _WINNING:
            out.append(Signal(
                "struggling", "Both below .500",
                f"{a_name} and {h_name} are both under water this season.",
                evidence))
        else:
            leader, trailer = ((a_name, h_name) if ap > hp else (h_name, a_name))
            out.append(Signal(
                "edge", "Edge on record",
                f"{leader} come in ahead of {trailer} on record.", evidence))
    return out


def _rank_signals(game: SlateGame, away: Standing, home: Standing) -> list[Signal]:
    a_name, h_name = _side_name(game, "away"), _side_name(game, "home")
    if away.is_ranked and home.is_ranked:
        return [Signal(
            "ranked_pair", "Ranked matchup",
            f"#{away.rank} {a_name} meets #{home.rank} {h_name}.",
            (f"#{away.rank} {a_name}", f"#{home.rank} {h_name}"))]
    for s, name, other in ((away, a_name, h_name), (home, h_name, a_name)):
        if s.is_ranked and s.rank is not None and s.rank <= _RANKED_TOP:
            return [Signal(
                "ranked_one", f"#{s.rank} in action",
                f"#{s.rank} {name} face {other}.", (f"#{s.rank} {name}",))]
    return []


def _stakes_signals(game: SlateGame) -> list[Signal]:
    out: list[Signal] = []
    if game.is_postseason:
        out.append(Signal("postseason", "Postseason",
                          game.round_name or "A postseason game.", ()))
    if game.conference_game:
        out.append(Signal("conference", "Conference game",
                          "Counts in the conference standings.", ()))
    return out


def _caveats(game: SlateGame, away: Standing, home: Standing) -> tuple[str, ...]:
    out: list[str] = []
    if not away.record and not home.record:
        out.append("No team records published for this league — nothing to compare.")
    elif away.win_pct is None or home.win_pct is None:
        played = max(away.games, home.games)
        out.append(f"Too early to read: {played} game{'' if played == 1 else 's'} played "
                   f"(need {MIN_GAMES}).")
    out.append("Team records only — no injuries, rest, weather or betting markets.")
    return tuple(out)


def league_norms(games: list[SlateGame]) -> dict[str, LeagueNorm]:
    """Each league's record spread, measured from the teams actually on the slate.

    Derived from the slate rather than hardcoded per sport, so a new league needs no
    tuning and an unusual season is described as it is. Leagues with too few teams
    present are still returned, but report ``usable`` False and are then scored on
    raw win percentage — comparable within themselves, not across.
    """
    seen: dict[str, dict[str, float]] = {}
    for game in games:
        away, home = standings(game)
        for side, standing in ((game.away_name or game.away_short, away),
                               (game.home_name or game.home_short, home)):
            if standing.win_pct is None or not side:
                continue
            seen.setdefault(game.league, {})[side] = standing.win_pct

    out: dict[str, LeagueNorm] = {}
    for league, teams in seen.items():
        values = list(teams.values())
        n = len(values)
        mean = sum(values) / n
        var = sum((v - mean) ** 2 for v in values) / n
        out[league] = LeagueNorm(league, round(mean, 4), round(var ** 0.5, 4), n)
    return out


def interest(game: SlateGame, norm: LeagueNorm | None = None) -> GameInterest:
    """Rank one game's claim on the reader's attention, with its reasoning.

    The score is a transparent blend of three inspectable parts: how good the two
    sides are, how evenly matched they are, and what is at stake. A game we know
    nothing about scores 0 and says so, rather than being quietly ranked mid-table.

    ``norm`` makes the score comparable across sports by judging each team against its
    own league's spread. Without it the score is still correct *within* a league but
    must not be compared between them — see ``LeagueNorm``.
    """
    away, home = standings(game)
    ap, hp = away.win_pct, home.win_pct
    if norm is not None and norm.usable:
        ap, hp = norm.strength(ap), norm.strength(hp)

    components: dict[str, float] = {}
    if ap is not None and hp is not None:
        # Quality: how good the pair is on average.
        quality = (ap + hp) / 2
        components["quality"] = round(quality, 3)
        # Competitiveness: how evenly matched they are, **weighted by how good they
        # are**. Closeness alone is not interesting — two 2-9 teams are perfectly
        # matched and the least watchable game on the slate. Scaling by quality is
        # what stops "evenly bad" from ranking like "evenly good".
        closeness = 1.0 - min(abs(ap - hp), 1.0)
        components["competitiveness"] = round(closeness * quality, 3)
    rank_pts = 0.0
    if away.is_ranked and home.is_ranked:
        rank_pts = 1.0
    elif away.is_ranked or home.is_ranked:
        best = min([r for r in (away.rank, home.rank) if r is not None], default=None)
        rank_pts = 0.6 if best is not None and best <= _RANKED_TOP else 0.35
    if rank_pts:
        components["rank"] = rank_pts
    stakes = 0.0
    if game.is_postseason:
        stakes += 1.0
    if game.conference_game:
        stakes += 0.35
    if game.neutral_site:
        stakes += 0.15
    if stakes:
        components["stakes"] = round(min(stakes, 1.0), 3)

    # Weighted blend over whichever components we actually have. Weights are flat and
    # few on purpose: this ranks a slate, it does not model an outcome.
    weights = {"quality": 0.40, "competitiveness": 0.25, "rank": 0.20, "stakes": 0.15}
    available = {k: w for k, w in weights.items() if k in components}
    score = 0
    if available:
        total = sum(available.values())
        score = round(100 * sum(components[k] * w for k, w in available.items()) / total)

    signals = tuple(_rank_signals(game, away, home)
                    + _quality_signals(game, away, home)
                    + _stakes_signals(game))
    return GameInterest(score=score, components=components, signals=signals,
                        caveats=_caveats(game, away, home))


# Signals worth a card chip. The card answers "is this worth watching?", so it shows
# only the draws — an ordinary or discouraging read stays on the game page, where
# there is room for its evidence and caveats. Same discipline as notable_context:
# a label that appears on every card teaches the reader to ignore the slot.
#
# "even" is deliberately absent. Closeness is not notable by itself, and the
# threshold cannot mean the same thing in every sport: MLB's whole league sits
# between roughly .380 and .620, so a .100 gap covers half of baseball and tagged 9
# of 15 cards, while in football it is a rounding error. Both-good-and-close is
# already "marquee", which travels correctly.
_CARD_WORTHY = ("ranked_pair", "ranked_one", "marquee", "upset_setup")


def card_signal(game: SlateGame) -> Signal | None:
    """The one signal worth a chip on this game's card, or None.

    Cross-league note: this returns a *label*, never a score, on purpose. Win
    percentage is not comparable across sports — baseball's best team is around .620
    while a college football team reaches .900 — so ranking a mixed slate by score
    would quietly favour the high-variance sports rather than reflect merit. A chip
    makes a claim only about its own game.
    """
    by_kind = {s.kind: s for s in interest(game).signals}
    for kind in _CARD_WORTHY:
        if kind in by_kind:
            return by_kind[kind]
    return None


def rank_games(games: list[SlateGame]) -> list[tuple[SlateGame, GameInterest]]:
    """Slate ordered by attention, most interesting first.

    Games we know nothing about (score 0) keep their place in the list rather than
    being dropped — the slate stays complete and their emptiness is visible.
    """
    norms = league_norms(games)
    scored = [(g, interest(g, norms.get(g.league))) for g in games]
    scored.sort(key=lambda pair: (pair[1].score, len(pair[1].signals)), reverse=True)
    return scored


def cross_league_comparable(games: list[SlateGame]) -> bool:
    """Whether every league on this slate has enough teams present to be normalised.

    When false, the ranking is still right inside each league but a single "best game
    of the day" across them would be comparing sports rather than teams — so callers
    that make a cross-league claim should check this first.
    """
    norms = league_norms(games)
    leagues = {g.league for g in games if any(standings(g))}
    return bool(norms) and all(norms.get(l) and norms[l].usable for l in leagues)


def best_game(games: list[SlateGame], minimum: int = 55) -> tuple[SlateGame, GameInterest] | None:
    """The single game most worth attention, or None when nothing clears the bar.

    Honouring "the app may say there are no strong opportunities": a slate of
    lopsided or unknown fixtures produces no pick at all.
    """
    for game, detail in rank_games(games):
        if detail.score >= minimum and detail.signals:
            return game, detail
    return None
