"""What the opponent is actually worth to an individual player.

**The measurement this is built on** (2026-08-19, 3 ingested seasons). A defence is rated
by how far players fell short of — or beat — *their own* baselines against it. That
removes the confound that a defence's schedule decides who it faced: rating it against
league average instead credits a defence for having played weak opponents.

Defences are a real, persistent trait (split-half r .14–.52 depending on the facet). What
that trait is *worth to a player* varies enormously, and this is the finding the module
exists to encode:

| stat | corr with a player's miss vs his own form | easiest-fifth minus hardest-fifth | game sd |
|---|---|---|---|
| passing yards | +0.17 | **+43 yds** | 96.9 |
| rushing yards | +0.08 | **+10 yds** | 39.1 |
| receiving yards | +0.02 | +2 yds | 35.3 |
| receptions | +0.03 | +0.3 | 2.5 |
| rush attempts | +0.03 | +0.6 | 6.7 |

So **the matchup moves quarterbacks and running backs, and does not meaningfully move
receivers or usage.** Every fantasy surface publishes a receiver matchup rating; across
three seasons here it is worth two yards against a 35-yard game-to-game swing, which is
below the noise floor of a single game. Usage is a coaching decision and defences do not
move it at all.

**And the effect is one-sided.** Splitting the full spectrum by how soft or tough the
defence is — mean gap against the player's own baseline, with 95% intervals:

| defence | passing yards | rushing yards |
|---|---|---|
| very tough | **−15.1 ±10.5** | **−4.0 ±3.0** |
| tough | **−21.6 ±12.9** | −2.0 ±3.2 |
| average | −3.1 ±8.6 | −0.9 ±2.4 |
| soft | −4.3 ±14.6 | +1.7 ±4.0 |
| very soft | +4.5 ±15.5 | +1.8 ±3.9 |

**A tough defence reliably suppresses. A soft one does nothing.** Every soft-side interval
covers zero, and the merely-soft passing band is *negative*. The plausible reason is game
script: a bad defence often means a lead, and a lead means running the ball and resting
starters, which cancels the matchup it created.

So this module makes **only negative calls**. "He faces a bad defence, expect a big day"
is the single most common claim in football previews and three seasons of this data do not
support it. Saying so is worth more than a rating that is really zero — the product rule
is that negative evidence is at least as prominent as supporting evidence, and here the
negative evidence is *all* the evidence.

Leakage: a defence's rating uses only games strictly before the one being described, so a
page can never rate a defence using the game it is previewing.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# stat → (positions that accumulate it, baseline floor for "a real contributor",
#         how tough the defence must be before we will say anything, in sd of the rating)
#
# The thresholds are the bands whose confidence interval excluded zero, per stat, not a
# round number: passing holds up from −0.5 sd, rushing only at the very toughest −1.0.
RATED = {
    "passing_yds": (("QB",), 100.0, -0.5),
    "rushing_yds": (("RB",), 20.0, -1.0),
}
# Measured, and deliberately not rated. Kept here so the page can *say* they are flat
# rather than silently omitting them, and so a future re-test has the old numbers.
UNRATED = {
    "receiving_yds": 1.6,
    "receiving_rec": 0.3,
    "rushing_att": 0.6,
}
_MIN_DEFENCE_GAMES = 10      # player-games against that defence before it is rated at all
_MIN_PLAYER_GAMES = 5
# A defence is rated on its most recent N qualifying player-games, not its whole history.
# Two problems, one fix: an unweighted all-time mean is dominated by seasons whose roster
# and coordinator are gone, while a current-season-only rating has nothing to say until
# about week 10 (a defence faces roughly one qualifying quarterback per game). A rolling
# window carries last season early and has fully turned over by midseason.
_DEFENCE_WINDOW = 34



@dataclass(frozen=True)
class MatchupCall:
    """One player's matchup outlook for one stat."""
    player: str
    position: str
    stat: str
    label: str                 # "Pass Yards"
    # "struggle" | "favourable-but-flat" | "neutral" | "not-a-factor".
    # There is deliberately no "excel": see the module docstring: soft defences produced
    # nothing measurable, so the page never promises an above-baseline day.
    direction: str
    swing: float               # expected yards above/below his own baseline
    baseline: float            # his own recent per-game average
    defence_rank: int | None   # 1 = the softest defence faced this stat
    defence_total: int | None
    evidence: str

    @property
    def is_call(self) -> bool:
        """Whether this is an actual prediction, as opposed to a stated non-finding."""
        return self.direction == "struggle"


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def defence_ratings(pg: pd.DataFrame, stat: str, before: str) -> pd.Series:
    """Each defence's rating for ``stat``: mean player over/under-performance against it.

    Positive means players beat their own baselines against this defence — a soft
    matchup. Uses only games strictly before ``before``.
    """
    positions, floor, _ = RATED[stat]
    f = pg[pg["position"].astype(str).str.upper().isin(positions)].copy()
    f = f[f["game_date"].astype("string") < str(before)]
    f["v"] = _num(f[stat])
    f = f.dropna(subset=["v"]).sort_values("game_date")
    if f.empty:
        return pd.Series(dtype=float)
    grp = f.groupby("player_id")["v"]
    # Expanding mean of prior games only — a player never contributes to a rating using
    # the game being rated.
    f["base"] = grp.transform(lambda s: s.shift(1).expanding().mean())
    f["n"] = grp.transform(lambda s: s.shift(1).expanding().count())
    f = f.dropna(subset=["base"])
    f = f[(f["n"] >= _MIN_PLAYER_GAMES) & (f["base"] >= floor)]
    if f.empty:
        return pd.Series(dtype=float)
    f["gap"] = f["v"] - f["base"]
    recent = f.groupby("opponent", group_keys=False).tail(_DEFENCE_WINDOW)
    agg = recent.groupby("opponent")["gap"].agg(["mean", "size"])
    return agg[agg["size"] >= _MIN_DEFENCE_GAMES]["mean"].sort_values(ascending=False)


def _rank(ratings: pd.Series, defence: str) -> tuple[int | None, int | None]:
    """1 = softest. ``None`` when this defence has too little history to rank."""
    if defence not in ratings.index:
        return None, None
    order = list(ratings.index)
    return order.index(defence) + 1, len(order)


def _describe(stat: str, rating: float, sd: float, rank, total) -> tuple[str, str]:
    """(direction, evidence) for a rated stat. Only ever negative or neutral."""
    noun = "pass defence" if stat == "passing_yds" else "run defence"
    _positions, _floor, cutoff = RATED[stat]
    where = ""
    if rank and total:
        # Rank 1 is softest, so a low rank number is a *good* matchup for the player.
        # "1st-softest" is not English; the extreme gets the bare superlative.
        def place(n: int, word: str) -> str:
            return f", {word} {noun} of {total}" if n == 1 else \
                   f", {_ordinal(n)}-{word} {noun} of {total}"
        if rank <= max(total // 4, 1):
            where = place(rank, "softest")
        elif rank >= total - max(total // 4, 1) + 1:
            where = place(total - rank + 1, "toughest")
    if sd <= 0:
        return "neutral", f"Opponent {noun} is around league average"
    z = rating / sd
    if z <= cutoff:
        return "struggle", (f"Players lose {abs(rating):.0f} yards against their own form "
                            f"facing this {noun}{where}")
    if z >= -cutoff:
        # A soft matchup is the one claim this data refuses to support, so it is named
        # rather than passed off as "neutral" — the reader can see we looked.
        return "favourable-but-flat", (
            f"A soft matchup on paper{where} — but across three seasons, soft defences "
            f"have not produced above-baseline games, so we make no call")
    return "neutral", f"Opponent {noun} is around league average{where}"


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }".replace(" ", "")


def ratings_for(pg: pd.DataFrame, before: str) -> dict[str, pd.Series]:
    """Every rated stat's defence table for one as-of date.

    Built once per page and handed to each player. Recomputing it per player made a
    matchup page ~0.7s and put a full archive export near ten minutes; the ratings do not
    vary by player, only by date.
    """
    return {stat: defence_ratings(pg, stat, before) for stat in RATED}


def outlook(pg: pd.DataFrame, player_id: str, player: str, position: str,
            opponent: str, before: str,
            ratings: dict[str, pd.Series] | None = None) -> MatchupCall | None:
    """This player's matchup outlook, or ``None`` when he plays no rated stat.

    Receivers return a ``not-a-factor`` call rather than nothing: the measured swing for
    receiving is ~2 yards against a 35-yard game sd, and saying so is more useful than an
    invented rating or an unexplained silence.
    """
    pos = str(position).upper()
    stat = next((s for s, (positions, _f, _sw) in RATED.items() if pos in positions), None)
    if stat is None:
        if pos in ("WR", "TE"):
            return MatchupCall(player, pos, "receiving_yds", "Rec Yards", "not-a-factor",
                               0.0, 0.0, None, None,
                               "Matchup is not a factor for receivers — measured at "
                               "~2 yards between the softest and toughest defences, "
                               "against a 35-yard game-to-game swing")
        return None

    _positions, floor, full_swing = RATED[stat]
    own = pg[(pg["player_id"].astype(str) == str(player_id))
             & (pg["game_date"].astype("string") < str(before))]
    values = _num(own[stat]).dropna()
    if len(values) < _MIN_PLAYER_GAMES:
        return None
    baseline = float(values.mean())
    if baseline < floor:
        return None

    ratings = (ratings or {}).get(stat)
    if ratings is None:
        ratings = defence_ratings(pg, stat, before)
    label = "Pass Yards" if stat == "passing_yds" else "Rush Yards"
    if ratings.empty or opponent not in ratings.index:
        return MatchupCall(player, pos, stat, label, "neutral", 0.0, baseline, None, None,
                           "Not enough history against this defence to rate the matchup")
    rating = float(ratings.loc[opponent])
    sd = float(ratings.std(ddof=0) or 0.0)
    rank, total = _rank(ratings, opponent)
    direction, evidence = _describe(stat, rating, sd, rank, total)
    # Report the defence's own measured rating, not the league-wide extreme: the +43 and
    # +10 headline figures are the softest-to-toughest span, and quoting them for an
    # average opponent would overstate the matchup by design.
    return MatchupCall(player, pos, stat, label, direction, rating, baseline,
                       rank, total, evidence)


def outlooks(pg: pd.DataFrame, players, opponent: str, before: str) -> tuple[MatchupCall, ...]:
    """Outlooks for an iterable of ``(player_id, player, position)``, sharing one rating
    table across all of them."""
    tables = ratings_for(pg, before)
    out = []
    for pid, name, pos in players:
        call = outlook(pg, pid, name, pos, opponent, before, tables)
        if call is not None:
            out.append(call)
    # Real calls first, then neutral, then the receivers' honest non-call.
    order = {"struggle": 0, "favourable-but-flat": 1, "neutral": 2, "not-a-factor": 3}
    return tuple(sorted(out, key=lambda c: (order[c.direction], -abs(c.swing))))
