"""Availability — knowing whether a player is in the game at all.

Written after the app's highest-rated WNBA play on 2026-08-09 (Kiah Stokes 4+
rebounds, biggest cushion on the board, five of five) turned out to be a player
listed Day-To-Day with a neck injury, in an endpoint already being called for other
things. A scoring history describes a player who is playing.
"""

from __future__ import annotations

import pandas as pd

from src.espn_injuries import InjuryReport, parse

_PAYLOAD = {"injuries": [
    {"team": {"displayName": "Home"}, "injuries": [
        {"status": "Out", "athlete": {"id": "111", "displayName": "Benched Player"},
         "details": {"type": "Coach's Decision"}},
        {"status": "Day-To-Day", "athlete": {"id": "222", "displayName": "Sore Star"},
         "details": {"type": "Neck", "returnDate": "2026-08-12"}},
    ]},
    {"team": {"displayName": "Away"}, "injuries": [
        {"status": "Out", "athlete": {"id": "333", "displayName": "Injured Starter"},
         "details": {"type": "Ankle"}},
        {"status": "Probable", "athlete": {"id": "444", "displayName": "Fine Player"},
         "details": {"type": "Knee"}},
    ]},
]}


def test_parses_out_and_questionable_separately():
    r = parse(_PAYLOAD)
    assert set(r.out) == {"111", "333"}
    assert set(r.questionable) == {"222"}
    assert "444" not in r.out and "444" not in r.questionable   # probable is noise


def test_status_lookup_is_by_athlete_id():
    """CLAUDE.md: never join on names. ESPN supplies the same ids our collector
    stores, so this is an exact id match or nothing."""
    r = parse(_PAYLOAD)
    assert r.status_for("222").name == "Sore Star"
    assert r.status_for(222).name == "Sore Star"      # tolerant of int/str
    assert r.status_for("999") is None


def test_a_record_without_an_id_is_ignored():
    r = parse({"injuries": [{"injuries": [
        {"status": "Out", "athlete": {"displayName": "Nameless"}}]}]})
    assert not r.known


def test_an_empty_report_is_not_a_clean_bill_of_health():
    """The distinction that keeps this honest: nothing known is not everyone fit."""
    assert not InjuryReport().known
    assert parse({}).known is False
    assert InjuryReport().status_for("111") is None


def test_notes_read_differently_for_out_and_questionable():
    r = parse(_PAYLOAD)
    assert "OUT" in r.status_for("333").note and "Ankle" in r.status_for("333").note
    q = r.status_for("222").note
    assert "Day-To-Day" in q and "Neck" in q and "unconfirmed" in q


# --- integration with the WNBA scorer -------------------------------------------

def _logs(player_id, values):
    return pd.DataFrame([{
        "player_id": player_id, "player_name": f"P{player_id}", "team_id": "T",
        "team": "Team", "team_abbr": "TM", "headshot": None, "game_id": f"g{i}",
        "game_date": f"2026-08-{i + 1:02d}T00:00Z", "minutes": 32, "points": v,
        "rebounds": 8, "assists": 5, "started": 1, "three_pointers_made": 1,
        "field_goals_attempted": 12, "three_pointers_attempted": 4,
        "free_throws_attempted": 3, "turnovers": 2,
    } for i, v in enumerate(values)])


def test_a_player_listed_out_gets_no_props():
    from src.wnba_opportunity import score_wnba_opportunities
    logs = _logs("111", [20] * 10)
    assert not score_wnba_opportunities(logs, ["Team"]).empty        # normally scored
    out = score_wnba_opportunities(logs, ["Team"], injuries=parse(_PAYLOAD))
    assert out.empty, "a player listed OUT must not be recommended at all"


def test_a_questionable_player_is_kept_but_flagged_first():
    from src.wnba_opportunity import score_wnba_opportunities
    out = score_wnba_opportunities(_logs("222", [20] * 10), ["Team"],
                                   injuries=parse(_PAYLOAD))
    assert not out.empty, "day-to-day is uncertainty, not absence"
    risks = list(out.iloc[0]["risks"])
    assert "Day-To-Day" in risks[0], risks    # leads: it reframes everything below


def test_an_unlisted_player_is_unaffected():
    from src.wnba_opportunity import score_wnba_opportunities
    out = score_wnba_opportunities(_logs("777", [20] * 10), ["Team"],
                                   injuries=parse(_PAYLOAD))
    assert not out.empty
    assert not any("Listed" in r for r in out.iloc[0]["risks"])
