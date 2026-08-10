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


# --- MLB roster availability -----------------------------------------------------

_ROSTER = {"roster": [
    {"person": {"id": 1, "fullName": "Active Guy"}, "status": {"code": "A", "description": "Active"}},
    {"person": {"id": 2, "fullName": "Hurt Guy"}, "status": {"code": "D10", "description": "Injured 10-Day"}},
    {"person": {"id": 3, "fullName": "Optioned Guy"}, "status": {"code": "RM", "description": "Reassigned to Minors"}},
    {"person": {"id": 4, "fullName": "No Status"}, "status": {}},
]}


def test_mlb_roster_marks_every_non_active_status_unavailable():
    """StatsAPI has no questionable tier — a day-to-day player stays active — so the
    split is active vs everything else, and nothing is inferred."""
    from src.mlb_injuries import parse as mlb_parse
    r = mlb_parse(_ROSTER)
    assert set(r.out) == {"2", "3"}
    assert r.status_for("1") is None          # active
    assert r.status_for("4") is None          # no status published -> no claim


def test_mlb_keeps_the_sources_own_wording_as_the_detail():
    from src.mlb_injuries import parse as mlb_parse
    r = mlb_parse(_ROSTER)
    assert r.status_for("2").detail == "Injured 10-Day"
    assert "Injured 10-Day" in r.status_for("2").note


def test_unavailable_batters_are_dropped_before_scoring():
    """Observed live: 12 of 40 scored batters for one game were on the injured list
    or in the minors. The lineup overlay caps them once lineups post, but before that
    they score normally and every one is written to the ledger only to void."""
    from src.mlb_injuries import parse as mlb_parse
    from src.opportunity import score_hit_opportunities
    rows = []
    for bid in (1, 2):
        for i in range(40):
            rows.append({"batter_id": bid, "batter_name": f"B{bid}", "batting_team": "HOU",
                         "game_id": f"g{i // 4}", "game_date": f"2026-08-{1 + i // 4:02d}",
                         "pa_number": i, "is_hit": 1 if i % 3 == 0 else 0,
                         "reached_base": 1 if i % 3 == 0 else 0, "is_strikeout": 0,
                         "pitch_count_pa": 4, "is_official_ab": 1})
    pa = pd.DataFrame(rows)
    assert len(score_hit_opportunities(pa, ["HOU"])) == 2
    out = score_hit_opportunities(pa, ["HOU"], availability=mlb_parse(_ROSTER))
    assert list(out["batter_id"]) == [1], "the injured batter must not be scored"


def test_no_availability_data_changes_nothing():
    from src.opportunity import score_hit_opportunities
    from src.availability import InjuryReport
    rows = [{"batter_id": 1, "batter_name": "B", "batting_team": "HOU",
             "game_id": f"g{i // 4}", "game_date": f"2026-08-{1 + i // 4:02d}",
             "pa_number": i, "is_hit": i % 3 == 0, "reached_base": i % 3 == 0,
             "is_strikeout": 0, "pitch_count_pa": 4, "is_official_ab": 1} for i in range(40)]
    pa = pd.DataFrame(rows)
    assert len(score_hit_opportunities(pa, ["HOU"], availability=InjuryReport())) == 1
    assert len(score_hit_opportunities(pa, ["HOU"], availability=None)) == 1
