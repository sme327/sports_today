"""The opponent's measured effect on an individual player.

These tests encode a finding that is easy to get backwards: the matchup signal in football
is **one-sided**. A tough defence reliably suppresses; a soft one produces nothing. A page
that promises a big day against a bad defence is making the most common claim in football
previews, and three seasons of this data do not support it.
"""

from __future__ import annotations

import pandas as pd
import pytest

from services import nfl_matchup as M


def _games(player, position, stat, values, opponents, team="Team A", start=1):
    return pd.DataFrame([{
        "player_id": player.lower().replace(" ", "-"), "player": player,
        "position": position, "team": team, "opponent": opponents[i % len(opponents)],
        "game_date": f"2025-09-{start + i:02d}", "season": 2025, "week": i + 1,
        stat: v,
    } for i, v in enumerate(values)])


def _league(stat, position, tough, soft, n=14):
    """A league where `tough` holds players well under their baseline and `soft` does not."""
    frames = []
    for p in range(6):
        # Each player alternates opponents so both defences get a comparable sample.
        vals, opps = [], []
        for i in range(n):
            opp = tough if i % 2 else soft
            base = 250.0 if stat == "passing_yds" else 70.0
            vals.append(base - (60 if opp == tough else 0))
            opps.append(opp)
        frames.append(_games(f"P{p}", position, stat, vals, opps))
        frames[-1]["opponent"] = opps
    return pd.concat(frames, ignore_index=True)


def test_a_tough_defence_produces_a_negative_call():
    pg = _league("passing_yds", "QB", "Tough D", "Soft D")
    call = M.outlook(pg, "p0", "P0", "QB", "Tough D", "2025-12-01")
    assert call is not None and call.direction == "struggle"
    assert call.is_call
    assert "lose" in call.evidence


def test_a_soft_defence_never_promises_a_big_day():
    """The finding this module exists for: soft-side intervals all covered zero, so the
    page states the non-finding instead of inventing an 'excel' call."""
    pg = _league("passing_yds", "QB", "Tough D", "Soft D")
    call = M.outlook(pg, "p0", "P0", "QB", "Soft D", "2025-12-01")
    assert call is not None
    assert call.direction != "excel"
    assert not call.is_call


def test_no_call_is_ever_positive():
    """A guard, not a detail: there is no code path that predicts an above-baseline day."""
    pg = _league("passing_yds", "QB", "Tough D", "Soft D")
    for opp in ("Tough D", "Soft D"):
        call = M.outlook(pg, "p0", "P0", "QB", opp, "2025-12-01")
        assert call.direction in ("struggle", "favourable-but-flat", "neutral",
                                  "not-a-factor")


def test_receivers_are_told_the_matchup_does_not_matter():
    """Measured at ~2 yards against a 35-yard game sd. Silence would read as an oversight,
    and a rating would be a number that is really zero."""
    pg = _league("receiving_yds", "WR", "Tough D", "Soft D")
    call = M.outlook(pg, "p0", "P0", "WR", "Tough D", "2025-12-01")
    assert call is not None and call.direction == "not-a-factor"
    assert "not a factor" in call.evidence


def test_a_defence_rating_never_uses_the_game_it_describes():
    pg = _league("passing_yds", "QB", "Tough D", "Soft D")
    before = M.defence_ratings(pg, "passing_yds", "2025-09-05")
    everything = M.defence_ratings(pg, "passing_yds", "2099-01-01")
    assert len(before) < len(everything) or before.empty


def test_an_unrated_defence_says_so_rather_than_guessing():
    pg = _league("passing_yds", "QB", "Tough D", "Soft D")
    call = M.outlook(pg, "p0", "P0", "QB", "Never Played", "2025-12-01")
    assert call.direction == "neutral"
    assert "not enough history" in call.evidence.lower()


def test_the_superlative_reads_as_english():
    assert M._ordinal(1) == "1st" and M._ordinal(2) == "2nd" and M._ordinal(11) == "11th"


def test_usage_and_receiving_are_recorded_as_measured_but_unrated():
    """Kept so a future re-test starts from the numbers, not from scratch."""
    assert set(M.UNRATED) == {"receiving_yds", "receiving_rec", "rushing_att"}
    assert all(v < 3 for v in M.UNRATED.values())
