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
# "Evenly matched" only means something between good teams. Measured against 191
# finished MLB games: closeness of record predicts nothing on its own, and tightening
# it makes matters worse — gap<=.100 gave a 3.45 mean margin against 3.25 for everything
# else, gap<=.050 gave 3.64, and a half-SD normalised gap gave 4.06 against a 3.39 base.
# Quality is what predicts a close game: both sides at league strength >= 0.55 gave 2.91.
# Two *good* teams play close games; two similarly-rated ones do not.
# _EVEN_MIN_STRENGTH tightens "close" into "close between good teams"; _MARQUEE_MIN
# is the same treatment for the top of the league. Both pair with an absolute raw
# floor — see _both_clear.
_EVEN_MIN_STRENGTH = 0.55
_MARQUEE_MIN_STRENGTH = 0.65
_WIDE = 0.300          # win-pct gap that makes a game lopsided on paper
_RANKED_TOP = 10       # "top-10" for poll-rank purposes
# How far below their overall rate a home side can be before home court stops
# counting as a point in their favour. Small: this is a veto on a weak claim, not a
# claim of its own.
_HOME_EDGE_TOL = 0.02

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


def home_edge(game: SlateGame) -> float | None:
    """How much better the home side is at home than overall, in win pct.

    Positive means home court is worth something to them; negative means it is not.
    ``None`` when the split is not published, and the caller must then not claim a
    home advantage either way.
    """
    overall = parse_record(game.home_record)
    at_home = parse_record(game.home_home_record)
    if overall.win_pct is None or at_home.games < MIN_GAMES:
        return None
    home_pct = (at_home.wins + 0.5 * at_home.ties) / at_home.games
    return round(home_pct - overall.win_pct, 4)


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


def _quality_signals(game: SlateGame, away: Standing, home: Standing,
                     norm: LeagueNorm | None = None) -> list[Signal]:
    """Signals that need both records to be real."""
    ap, hp = away.win_pct, home.win_pct
    if ap is None or hp is None:
        return []
    a_name, h_name = _side_name(game, "away"), _side_name(game, "home")
    evidence = (_rec(a_name, away), _rec(h_name, home))
    gap = abs(ap - hp)
    out: list[Signal] = []

    if _both_clear(away, home, norm, _MARQUEE_MIN_STRENGTH, _WINNING, _STRONG):
        out.append(Signal(
            "marquee", "Marquee matchup",
            f"Two of the best teams in the league: {a_name} and {h_name}.",
            evidence))
    elif min(ap, hp) >= _WINNING:
        # The broad middle, where most professional games live. Without this a
        # 6-5 vs 8-3 game scored well and explained nothing.
        out.append(Signal(
            "solid", "Winning records",
            f"Both {a_name} and {h_name} come in above .500.",
            evidence))
    if gap <= _CLOSE and _both_clear(away, home, norm, _EVEN_MIN_STRENGTH, _WINNING, _WINNING):
        out.append(Signal(
            "even", "Evenly matched",
            f"{a_name} and {h_name} are closely matched, and both are good.",
            evidence))
    if gap >= _WIDE:
        stronger, weaker = ((a_name, h_name) if ap > hp else (h_name, a_name))
        weaker_is_home = (hp < ap)
        # An upset is only a story when the favourite is actually good. Without this
        # a 5-6 side hosting a 8-3 side read as an "upset setup", which fired on 10
        # of 45 college games and cheapened the label.
        favourite_is_strong = max(ap, hp) >= _STRONG
        # The home angle is only worth making when the home side is actually better
        # at home. Observed live: a 12-19 team hosting was framed as an upset setup
        # while being 5-10 at home — worse than their own overall — and they lost.
        edge = home_edge(game)
        home_is_a_factor = weaker_is_home and (edge is None or edge >= -_HOME_EDGE_TOL)
        if favourite_is_strong and (home_is_a_factor or game.neutral_site):
            where = "at home" if weaker_is_home and not game.neutral_site else "on a neutral field"
            detail = f"{stronger} are much stronger on record, but {weaker} are {where}."
            ev = evidence + ((f"{weaker} {game.home_home_record} at home",)
                             if weaker_is_home and game.home_home_record else ())
            out.append(Signal(
                "upset_setup", "Upset setup", detail, ev,
                caveats=("A record gap describes the season so far, not tonight — "
                         "no injury, rest or matchup context is included.",)))
        elif favourite_is_strong and weaker_is_home and game.home_home_record:
            # Weaker side at home, but home is no help to them — say so plainly
            # rather than dressing it as an upset.
            out.append(Signal(
                "mismatch", "Lopsided on paper",
                f"{stronger} come in far ahead, and {weaker} are no better at home "
                f"({game.home_home_record}).",
                evidence + (f"{weaker} {game.home_home_record} at home",),
                caveats=("Record gap only; nothing here accounts for injuries or "
                         "how the teams match up.",)))
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


def _both_clear(away: Standing, home: Standing, norm: LeagueNorm | None,
                strength_bar: float, raw_floor: float, raw_fallback: float) -> bool:
    """Whether both sides clear a quality bar, judged against their own league.

    Raw win percentage cannot carry this alone: .650 is unreachable in baseball and
    ordinary in basketball, which left ``marquee`` firing on **zero** of 191 MLB games.
    So the bar is league-relative strength where the slate supports a norm.

    Three bars, because each covers a different failure. ``raw_floor`` is absolute: a
    losing team is not "good" however weak its peers are, and a relative bar alone would
    crown the least-poor side on a slate of bad teams. ``strength_bar`` is relative, and
    is what makes one signal mean the same thing in two sports. ``raw_fallback`` applies
    only when the slate is too small to normalise, where a strict absolute bar is all
    that is left — so it must be the conservative one.
    """
    ap, hp = away.win_pct, home.win_pct
    if ap is None or hp is None:
        return False
    if min(ap, hp) < raw_floor:
        return False
    if norm is not None and norm.usable:
        sa, sh = norm.strength(ap), norm.strength(hp)
        if sa is not None and sh is not None:
            return min(sa, sh) >= strength_bar
    return min(ap, hp) >= raw_fallback


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
                    + _quality_signals(game, away, home, norm)
                    + _stakes_signals(game))
    return GameInterest(score=score, components=components, signals=signals,
                        caveats=_caveats(game, away, home))


# Signals worth a card chip. The card answers "is this worth watching?", so it shows
# only the draws — an ordinary or discouraging read stays on the game page, where
# there is room for its evidence and caveats. Same discipline as notable_context:
# a label that appears on every card teaches the reader to ignore the slot.
#
# "even" was excluded while it meant nothing but closeness: MLB's whole league sits
# between roughly .380 and .620, so a .100 gap covered half of baseball and tagged 9 of
# 15 cards. It now also requires both sides to be good against their own league, which
# cut it to 31 of 191 MLB games and turned it from the worst predictor of a close game
# into one of the best (2.84 mean margin against a 3.39 base). It travels, so it earns
# a chip — but only when a norm is available, which is what makes it league-relative.
_CARD_WORTHY = ("ranked_pair", "ranked_one", "marquee", "even", "upset_setup")

# Kinds that may only claim a chip when the slate could actually be normalised. Their
# un-normalised fallback is an absolute win-percentage bar, and .508 vs .517 clears it
# while being the most ordinary pairing in baseball. On the game page that is harmless —
# the evidence is right there to read. A chip has no room to qualify itself, so it
# stays silent rather than overclaim.
_CARD_NEEDS_NORM = ("even",)

# Signals that can justify calling a game the best one. Normalisation is relative to
# the league, so on a slate where every team is poor the least-poor game still scores
# well — and would be marked "Best game" on the strength of "Both below .500". A best
# game needs a positive reason, not merely the highest number.
_BEST_WORTHY = ("ranked_pair", "ranked_one", "marquee", "even", "solid", "upset_setup")


def card_signal(game: SlateGame, norm: LeagueNorm | None = None) -> Signal | None:
    """The one signal worth a chip on this game's card, or None.

    Pass ``norm`` wherever the whole slate is in hand. Without it the quality signals
    fall back to absolute win-percentage bars, and those do not travel: ``marquee``
    needs .650 raw, which no MLB team reaches, so an un-normalised card could never
    show one all season.

    Cross-league note: this returns a *label*, never a score, on purpose. Win
    percentage is not comparable across sports — baseball's best team is around .620
    while a college football team reaches .900 — so ranking a mixed slate by score
    would quietly favour the high-variance sports rather than reflect merit. A chip
    makes a claim only about its own game.
    """
    normalised = norm is not None and norm.usable
    by_kind = {s.kind: s for s in interest(game, norm).signals}
    for kind in _CARD_WORTHY:
        if kind in by_kind and (normalised or kind not in _CARD_NEEDS_NORM):
            return by_kind[kind]
    return None


def best_per_league(games: list[SlateGame], minimum: int = 55
                    ) -> tuple[dict[str, str], list[str]]:
    """``({league: game_id}, [leagues we could not judge])``.

    Marked per league rather than across the slate because a single "game of the day"
    asserts leagues are comparable, and on a light day they are not — today the WNBA
    had four of its teams playing, far too few to normalise. Naming a best game inside
    one league is always a fair comparison; naming one across leagues often is not.

    A league appears in the second list when it is playing but cannot be judged, so the
    UI can say so rather than silently omitting it.
    """
    picks: dict[str, str] = {}
    unjudged: list[str] = []
    for league in sorted({g.league for g in games}):
        pick = best_game_in_league(games, league, minimum=minimum)
        if pick:
            picks[league] = str(pick[0].game_id)
        elif any(g.league == league for g in games):
            norm = league_norms([g for g in games if g.league == league]).get(league)
            if norm is None or not norm.usable:
                unjudged.append(league)
    return picks, unjudged


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
    """The single game most worth attention, or None when we cannot honestly name one.

    Returns None in three cases, all of them deliberate:

    - nothing clears ``minimum`` ("the app may say there are no strong opportunities");
    - the leading game has no signal, so there would be nothing to say about it;
    - **the slate spans leagues we cannot compare** — picking a single best game across
      leagues asserts they are comparable, and when one of them has too few teams on
      the slate to normalise, that assertion is false. The guard existed but callers
      had to remember it, which is not a guard. Enforced here instead.
    """
    # Only a multi-league slate makes a cross-league claim. Within one league the
    # scores are comparable by construction, so the guard must not fire there — an
    # over-strict version refused a perfectly fair three-game single-league slate.
    leagues = {g.league for g in games}
    if len(leagues) > 1 and not cross_league_comparable(games):
        return None
    for game, detail in rank_games(games):
        if detail.score >= minimum and any(s.kind in _BEST_WORTHY for s in detail.signals):
            return game, detail
    return None


def best_game_in_league(games: list[SlateGame], league: str,
                        minimum: int = 55) -> tuple[SlateGame, GameInterest] | None:
    """The best game within one league, which is always a fair comparison.

    Useful when the slate as a whole cannot be compared but a single league on it
    still can — the common case on a light day.
    """
    subset = [g for g in games if g.league == league]
    norm = league_norms(subset).get(league)
    if norm is None or not norm.usable:
        return None
    scored = sorted(((g, interest(g, norm)) for g in subset),
                    key=lambda p: (p[1].score, len(p[1].signals)), reverse=True)
    for game, detail in scored:
        if detail.score >= minimum and any(s.kind in _BEST_WORTHY for s in detail.signals):
            return game, detail
    return None
