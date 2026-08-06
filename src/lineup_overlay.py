"""Shared confirmed-lineup overlay for batter markets (1+ Hit, Total Bases, …).

Given today's posted lineups, adds slot evidence for a confirmed hitter, caps a
batter who's been scratched from a posted lineup, and reports the slot/posted state
so each scorer can word its own "context not yet included" fallback. Kept in one
place so every batter market treats lineups identically. Leakage-safe by
construction — the caller supplies today's lineup for today's game.
"""

from __future__ import annotations

from src.mlb_lineups import Lineups

# When a batter is confirmed out of today's lineup, cap the score so a strong
# history can't float a benched player to the top of the slate.
BENCH_SCORE_CAP = 25
BENCH_STABILITY_CAP = 40


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def slot_bonus(slot: int) -> int:
    """Small, evidence-first nudge for lineup slot (top of the order sees more
    plate appearances). Deliberately minor so recorded history stays dominant."""
    if slot <= 2:
        return 3
    if slot <= 5:
        return 2
    if slot <= 6:
        return 0
    return -3


def apply(batter_id, team_name: str, score: float, stability: int,
          support: list[str], risks: list[str],
          lineups: Lineups | None) -> tuple[int, int, int | None, bool]:
    """Apply the overlay in place on ``support``/``risks`` and return
    ``(score, stability, slot, team_posted)``. ``score`` comes in as the raw float
    and is rounded/clamped here (after the slot nudge)."""
    slot = lineups.slot.get(int(batter_id)) if lineups is not None else None
    team_posted = lineups.is_posted(team_name) if lineups is not None else False
    if slot is not None:
        support.insert(0, f"Batting {ordinal(slot)}, confirmed lineup")
        score += slot_bonus(slot)
    elif team_posted:                       # lineup is out and this bat isn't in it
        risks.insert(0, "Not in today's posted lineup")

    score = max(0, min(round(score), 100))
    if slot is None and team_posted:
        score = min(score, BENCH_SCORE_CAP)
        stability = min(stability, BENCH_STABILITY_CAP)
    return score, stability, slot, team_posted
