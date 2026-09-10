"""Hand-authored NFL game notes: availability, roster changes, a written read, and prop
leans for one game, read from ``content/nfl/<espn_event_id>.toml``.

Why this exists. The NFL engine builds a week-1 page from the *previous* season's feed,
and a feed cannot see an offseason: on 2026-09-09 it spotlighted a running back who had
signed elsewhere, a receiver who had been released, and a rookie ruled out that morning.
The honest fix for today is a dated, sourced, hand-entered note that (a) says who is out
or gone so the engine stops spotlighting them, and (b) carries the read a person wrote
for this game. Nothing here is consumed by scoring — the leans are text, ranked by the
author, and the page says so.

The pipe that would replace the hand entry (ESPN's injury report and current roster,
collected in the daily run) is the obvious next step; this module is the seam it would
fill. See docs/engineering/NFL_GAME_PAGE.md → "Game notes".
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from src.config import PROJECT_ROOT

NOTES_DIR = PROJECT_ROOT / "content" / "nfl"

# Statuses that remove a player from the engine's spotlights. "Questionable" does not:
# the player may play, and dropping him would be a prediction about the report.
SIDELINED = frozenset({"Out", "PUP", "IR", "Departed", "Suspended"})
_STATUSES = SIDELINED | {"Questionable", "Doubtful"}
_DIRECTIONS = frozenset({"over", "under"})
_BOARD_DIRECTIONS = _DIRECTIONS | {"pass"}
_CONFIDENCE = ("high", "moderate", "low")
# Two graded sections on the page. "leans" is the ranked list; "overs" is the separate
# block at the foot where the note goes looking for overs in the posted lines. Both are
# recorded and graded the same way; the ledger keeps them apart.
LEAN_SECTIONS = ("leans", "overs", "volume", "props")
# "props" is the single board (since 2026-09-10): every posted line evaluated, with
# over / under / pass. The three older lists still parse so tonight's note keeps its
# record; new notes should use the board only.
# The volume board's stats. Every posted line in one of these gets a call each week,
# whichever section it lands in; the ledger reports them together as "volume plays".
VOLUME_STATS = frozenset({"passing_att", "passing_comp", "receptions", "rushing_att"})
_PRELINE_DIRECTIONS = frozenset({"over", "under", "avoid"})

# The stats a lean may name — and therefore the only ones the ledger can grade. Each maps
# to the column the feed and the ESPN box score both carry (src/espn_nfl_boxscore). A
# stat outside this list is a typo or a market the grader cannot settle, and either one
# should fail loudly rather than record a lean nobody can grade.
LEAN_STATS: dict[str, str] = {
    "passing_yds": "passing yards",
    "passing_att": "pass attempts",
    "passing_comp": "completions",
    "passing_td": "passing touchdowns",
    "passing_int": "interceptions thrown",
    "rushing_yds": "rushing yards",
    "rushing_att": "rush attempts",
    "receptions": "receptions",
    "receiving_yds": "receiving yards",
}


@dataclass(frozen=True)
class Availability:
    team: str
    player: str
    position: str
    status: str                 # one of _STATUSES
    detail: str = ""
    # What this absence changes tonight, in one line. Set only where it changes the
    # read: the page ranks these above the rest, which collapse to a single line.
    impact: str = ""


@dataclass(frozen=True)
class RosterChange:
    team: str
    direction: str              # "in" | "out"
    text: str


@dataclass(frozen=True)
class PrelineRead:
    """A directional read written **before any line was posted** — no number, so it
    cannot be graded. Kept on the page, labelled as such, as a record of what the read
    was before the market spoke."""
    team: str
    player: str
    market: str                 # free text, e.g. "Rush attempts and receptions"
    direction: str              # "over" | "under" | "avoid"
    why: str


@dataclass(frozen=True)
class PropLean:
    """One gradeable call: a player, a stat, the posted line, and a side. ``market``
    is derived ("Under 2.5 receptions") so the page and the ledger never disagree
    about what was called."""
    team: str
    player: str
    stat: str                   # a key of LEAN_STATS
    line: float                 # the posted number, e.g. 2.5
    direction: str              # "over" | "under"
    confidence: str             # "high" | "moderate" | "low"
    why: str
    section: str = "leans"      # one of LEAN_SECTIONS

    @property
    def market(self) -> str:
        if self.direction == "pass":
            return f"{self.line:g} {LEAN_STATS[self.stat]}"
        return f"{self.direction.capitalize()} {self.line:g} {LEAN_STATS[self.stat]}"


@dataclass(frozen=True)
class Falsifier:
    """What would change the read: a condition to watch once the game starts, and
    what it does to the thesis. Not a prediction — the test of one."""
    condition: str
    consequence: str


@dataclass(frozen=True)
class Source:
    title: str
    url: str


@dataclass(frozen=True)
class GameNotes:
    game_id: str
    away: str
    home: str
    kickoff: str
    authored: str               # ISO date the note was written
    report_date: str            # ISO date of the official injury report it reflects
    availability: tuple[Availability, ...] = ()
    changes: tuple[RosterChange, ...] = ()
    shape_headline: str = ""
    shape: tuple[str, ...] = ()                       # plain lines (older notes)
    shape_observations: tuple[tuple[str, str], ...] = ()   # (lead, text) pairs
    shape_alternative: str = ""
    game_script: str = ""       # a hand-written expected shape, shown under The read
    falsifiers: tuple[Falsifier, ...] = ()
    preline: tuple[PrelineRead, ...] = ()
    leans: tuple[PropLean, ...] = ()
    sources: tuple[Source, ...] = ()
    fingerprint: str = field(default="", compare=False)

    def sidelined(self, team: str | None = None) -> frozenset[str]:
        """Names of players who must not be spotlighted: out, on a list, or gone."""
        return frozenset(a.player for a in self.availability
                         if a.status in SIDELINED and (team is None or a.team == team))

    def in_section(self, section: str) -> tuple[PropLean, ...]:
        return tuple(l for l in self.leans if l.section == section)

    @property
    def called(self) -> tuple[PropLean, ...]:
        """The entries that are actual calls (not passes) — what gets graded."""
        return tuple(l for l in self.leans if l.direction != "pass")


def notes_path(game_id: str, notes_dir: Path = NOTES_DIR) -> Path:
    return notes_dir / f"{game_id}.toml"


def _require(d: dict, key: str, where: str) -> str:
    if key not in d or d[key] in (None, ""):
        raise ValueError(f"{where}: missing '{key}'")
    return str(d[key])


def parse_notes(raw: bytes, where: str = "game notes") -> GameNotes:
    """Parse and validate a notes document. Fails clearly: a typo in a status or a
    direction would otherwise render as a chip the CSS has no style for, or silently
    keep spotlighting a player the note meant to remove."""
    d = tomllib.loads(raw.decode("utf-8"))
    avail = []
    for i, a in enumerate(d.get("availability", [])):
        w = f"{where} availability[{i}]"
        status = _require(a, "status", w)
        if status not in _STATUSES:
            raise ValueError(f"{w}: status '{status}' not in {sorted(_STATUSES)}")
        avail.append(Availability(_require(a, "team", w), _require(a, "player", w),
                                  str(a.get("position", "")), status, str(a.get("detail", "")),
                                  str(a.get("impact", "")).strip()))
    changes = []
    for i, c in enumerate(d.get("changes", [])):
        w = f"{where} changes[{i}]"
        direction = _require(c, "direction", w)
        if direction not in ("in", "out"):
            raise ValueError(f"{w}: direction must be 'in' or 'out'")
        changes.append(RosterChange(_require(c, "team", w), direction, _require(c, "text", w)))
    preline = []
    for i, r in enumerate(d.get("preline", [])):
        w = f"{where} preline[{i}]"
        direction = _require(r, "direction", w)
        if direction not in _PRELINE_DIRECTIONS:
            raise ValueError(f"{w}: direction '{direction}' not in {sorted(_PRELINE_DIRECTIONS)}")
        preline.append(PrelineRead(_require(r, "team", w), _require(r, "player", w),
                                   _require(r, "market", w), direction, _require(r, "why", w)))
    leans = []
    tables = [(name, l) for name in LEAN_SECTIONS for l in d.get(name, [])]
    for i, (table, l) in enumerate(tables):
        w = f"{where} {table}[{i}]"
        section = str(l.get("section") or table)
        if section not in LEAN_SECTIONS:
            raise ValueError(f"{w}: section '{section}' not in {list(LEAN_SECTIONS)}")
        direction = _require(l, "direction", w)
        allowed = _BOARD_DIRECTIONS if section == "props" else _DIRECTIONS
        if direction not in allowed:
            raise ValueError(f"{w}: direction '{direction}' not in {sorted(allowed)}")
        if section == "overs" and direction != "over":
            raise ValueError(f"{w}: the overs section holds overs only")
        stat = _require(l, "stat", w)
        if section == "volume" and stat not in VOLUME_STATS:
            raise ValueError(f"{w}: the volume board holds {sorted(VOLUME_STATS)} only")
        if stat not in LEAN_STATS:
            raise ValueError(f"{w}: stat '{stat}' not in {sorted(LEAN_STATS)}")
        # A pass carries no confidence: it is the absence of a call.
        confidence = "" if direction == "pass" else _require(l, "confidence", w)
        if confidence and confidence not in _CONFIDENCE:
            raise ValueError(f"{w}: confidence '{confidence}' not in {list(_CONFIDENCE)}")
        try:
            line = float(l["line"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"{w}: 'line' must be the posted number, e.g. 2.5") from None
        leans.append(PropLean(_require(l, "team", w), _require(l, "player", w),
                              stat, line, direction, confidence, _require(l, "why", w),
                              section))
    falsifiers = tuple(
        Falsifier(_require(f, "condition", f"{where} falsifiers[{i}]"),
                  _require(f, "consequence", f"{where} falsifiers[{i}]"))
        for i, f in enumerate(d.get("falsifiers", [])))
    read = d.get("read", {}) or {}
    shape = d.get("shape", {}) or {}
    sources = tuple(Source(_require(s, "title", f"{where} sources[{i}]"),
                           _require(s, "url", f"{where} sources[{i}]"))
                    for i, s in enumerate(d.get("sources", [])))
    return GameNotes(
        game_id=_require(d, "game_id", where),
        away=_require(d, "away", where), home=_require(d, "home", where),
        kickoff=_require(d, "kickoff", where),
        authored=_require(d, "authored", where),
        report_date=str(d.get("report_date", "") or d["authored"]),
        availability=tuple(avail), changes=tuple(changes),
        shape_headline=str(shape.get("headline", "")),
        shape=tuple(str(s) for s in shape.get("lines", [])),
        shape_observations=tuple(
            (str(o.get("lead", "")).strip(), str(o.get("text", "")).strip())
            for o in shape.get("observations", []) if o.get("text")),
        shape_alternative=str(shape.get("alternative", "")),
        game_script=str(read.get("game_script", "")).strip(),
        falsifiers=falsifiers,
        preline=tuple(preline), leans=tuple(leans), sources=sources,
        fingerprint=hashlib.sha1(raw).hexdigest()[:10],
    )


def load_notes(game_id: str | None, notes_dir: Path = NOTES_DIR) -> GameNotes | None:
    """The note for an ESPN event id, or None when nobody wrote one — which is every
    game but the ones a person sat down with. A malformed file raises: the tests run
    before a publish, and a broken note must not quietly publish a page without it."""
    if not game_id:
        return None
    path = notes_path(str(game_id), notes_dir)
    if not path.is_file():
        return None
    notes = parse_notes(path.read_bytes(), where=str(path))
    if notes.game_id != str(game_id):
        raise ValueError(f"{path}: game_id '{notes.game_id}' does not match the filename")
    return notes
