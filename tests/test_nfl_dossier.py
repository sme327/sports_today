"""The dossier's name normalisation — the check that catches an ESPN/feed suffix
mismatch, which is how four players were wrongly called departed on 2026-09-13."""

from __future__ import annotations

import pytest

from scripts.nfl_dossier import norm


@pytest.mark.parametrize("espn, feed", [
    ("James Cook III", "James Cook"),
    ("Travis Etienne Jr.", "Travis Etienne"),
    ("Aaron Jones Sr.", "Aaron Jones"),
    ("Oronde Gadsden", "Oronde Gadsden II"),
    ("Marvin Harrison Jr.", "Marvin Harrison"),
    ("Ja'Marr Chase", "JaMarr Chase"),
    ("A.J. Brown", "AJ Brown"),
    ("Michael Pittman Jr.", "Michael Pittman"),
])
def test_the_same_player_normalises_to_the_same_string(espn, feed):
    assert norm(espn) == norm(feed)


@pytest.mark.parametrize("a, b", [
    ("Josh Allen", "Keenan Allen"),
    ("Michael Carter", "Michael Carter II"),   # different players, and the check cannot know
    ("Chris Olave", "Chris Godwin"),
])
def test_different_players_stay_different(a, b):
    if a == "Michael Carter":
        # Documented false positive: a suffix really does distinguish these two, so the
        # dossier prints candidates for a human rather than deciding.
        assert norm(a) == norm(b)
    else:
        assert norm(a) != norm(b)


def test_a_nickname_is_not_caught_and_that_is_stated():
    """ESPN's "Kenny Gainwell" against the feed's "Kenneth" is a nickname, not a suffix.
    The check does not close this; the dossier's NAME MISMATCH line is what surfaces it."""
    assert norm("Kenny Gainwell") != norm("Kenneth Gainwell")
