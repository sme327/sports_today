"""The shared ESPN box-score collector.

Offline: every test builds its own payload and temp DB. Nothing here touches the network
or the real database.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from src.espn_boxscore import (SPORTS, clock_minutes,
                               collect, ensure_tables, made_attempted, number,
                               parse_event, parse_player_rows, stat_columns)

_GAME = {"game_id": "g1", "game_date": "2026-01-10T00:00Z", "season": 2025,
         "season_type": 2, "home_team_id": "1", "home_team": "Home Team",
         "away_team_id": "2", "away_team": "Away Team"}


def _payload(names, athletes, group_name="", team_id="1"):
    return {"boxscore": {"players": [{
        "team": {"id": team_id, "displayName": "Home Team", "abbreviation": "HOM"},
        "statistics": [{"name": group_name, "names": names, "athletes": athletes}]}]}}


def _athlete(pid, name, stats, **kw):
    return {"athlete": {"id": pid, "displayName": name}, "stats": stats, **kw}


# --- parsing primitives --------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("8-15", (8.0, 15.0)), ("3/5", (3.0, 5.0)), ("0-0", (0.0, 0.0)),
    ("7", (7.0, None)), ("", (None, None)), (None, (None, None)),
])
def test_made_attempted(raw, expected):
    assert made_attempted(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("28:34", 28 + 34 / 60), ("8:34", 8 + 34 / 60), ("31", 31.0),
    ("1:02:30", 62.5),        # a goalie can exceed an hour in a long overtime
    ("DNP", None), ("--", None), (None, None),
])
def test_clock_minutes(raw, expected):
    got = clock_minutes(raw)
    assert (got is None and expected is None) or abs(got - expected) < 1e-9


def test_number_handles_espn_leading_dot_rates():
    """ESPN writes save and faceoff rates as '.714', which float() rejects on some
    inputs and which must not silently become None — SV% is a real NHL stat."""
    assert number(".714") == pytest.approx(0.714)
    assert number("50.0") == 50.0
    assert number("--") is None
    assert number("DNP") is None


# --- the sport specs -----------------------------------------------------------------

def test_split_stats_expand_into_made_and_attempted_columns():
    cols = stat_columns(SPORTS["nba"])
    assert "field_goals_made" in cols and "field_goals_attempted" in cols
    assert "field_goals" not in cols
    assert "points" in cols


def test_college_basketball_declares_the_espn_group_and_limit_it_needs():
    """Without these ESPN returns 19 of 169 games and says nothing — verified against our
    own vendor feed. A CBB collector missing them is silently broken."""
    cbb = SPORTS["cbb"]
    assert cbb.groups == (50,)
    assert cbb.limit >= 300


def test_hockey_carries_both_skater_and_goalie_stats():
    nhl = SPORTS["nhl"]
    for stat in ("shots_on_goal", "goals", "assists", "hits", "blocked_shots"):
        assert stat in nhl.columns, stat
    for stat in ("saves", "shots_against", "save_pct"):
        assert stat in nhl.columns, stat
    # Ice time is a clock, not a count.
    assert "time_on_ice" in nhl.clock


# --- box-score parsing ---------------------------------------------------------------

def test_parses_a_basketball_box_score_into_the_declared_schema():
    payload = _payload(["MIN", "PTS", "FG", "3PT", "REB", "AST"],
                       [_athlete("99", "A Player", ["31", "20", "8-15", "1-5", "4", "4"])])
    rows = parse_player_rows(payload, _GAME, SPORTS["nba"])
    assert len(rows) == 1
    r = rows[0]
    assert r["player_id"] == "99" and r["minutes"] == 31.0 and r["points"] == 20.0
    assert r["field_goals_made"] == 8.0 and r["field_goals_attempted"] == 15.0
    assert r["home_away"] == "home" and r["opponent"] == "Away Team"


def test_skaters_and_goalies_land_in_one_table_tagged_by_group():
    """NHL ships two different stat sets in separate groups. One wide table keeps 'one row
    per player-game' — the shape every scorer expects — with `player_group` saying which."""
    skater = _payload(["TOI", "G", "A", "S", "HT"],
                      [_athlete("1", "Skater", ["18:04", "1", "2", "4", "3"])], "forwards")
    goalie = _payload(["SV", "SA", "SV%", "TOI"],
                      [_athlete("2", "Goalie", ["10", "14", ".714", "28:34"])], "goalies")
    payload = {"boxscore": {"players": [skater["boxscore"]["players"][0],
                                        goalie["boxscore"]["players"][0]]}}
    rows = {r["player_id"]: r for r in parse_player_rows(payload, _GAME, SPORTS["nhl"])}
    assert rows["1"]["player_group"] == "forwards"
    assert rows["1"]["shots_on_goal"] == 4.0 and rows["1"]["goals"] == 1.0
    assert rows["1"]["saves"] is None            # a skater has no save stats
    assert rows["2"]["player_group"] == "goalies"
    assert rows["2"]["saves"] == 10.0 and rows["2"]["save_pct"] == pytest.approx(0.714)


def test_an_athlete_without_an_id_is_dropped_never_joined_by_name():
    payload = _payload(["MIN", "PTS"], [
        {"athlete": {"displayName": "No Id"}, "stats": ["10", "5"]},
        _athlete("7", "Has Id", ["20", "9"]),
    ])
    rows = parse_player_rows(payload, _GAME, SPORTS["nba"])
    assert [r["player_id"] for r in rows] == ["7"]


def test_dnp_rows_are_kept_with_null_stats():
    """ESPN reports players who did not appear; the vendor feed omits them. Keeping them
    is the point — an absent availability signal caused a real WNBA windowing bug."""
    payload = _payload(["MIN", "PTS"], [_athlete("5", "Benched", ["--", "--"], active=0)])
    rows = parse_player_rows(payload, _GAME, SPORTS["nba"])
    assert len(rows) == 1
    assert rows[0]["minutes"] is None and rows[0]["points"] is None
    assert rows[0]["active"] == 0


def test_a_payload_with_no_player_section_returns_no_rows():
    """Ordinary for a postponed or unprocessed game. The caller records it as a failure so
    a completed game silently writing zero rows is visible."""
    assert parse_player_rows({"boxscore": {}}, _GAME, SPORTS["nba"]) == []


def test_unknown_stat_labels_are_ignored_not_crashed_on():
    """A vendor adding a column must not break the collector."""
    payload = _payload(["MIN", "PTS", "NEWSTAT"],
                       [_athlete("3", "P", ["25", "11", "42"])])
    rows = parse_player_rows(payload, _GAME, SPORTS["nba"])
    assert rows[0]["points"] == 11.0
    assert "newstat" not in rows[0]


def test_parse_event_flattens_a_scheduled_game():
    event = {"id": "401", "date": "2026-01-10T00:00Z",
             "season": {"year": 2025, "type": 2},
             "status": {"type": {"name": "STATUS_FINAL", "completed": True}},
             "competitions": [{"competitors": [
                 {"homeAway": "home", "team": {"id": "1", "displayName": "H"}, "score": "110"},
                 {"homeAway": "away", "team": {"id": "2", "displayName": "A"}, "score": "104"}],
                 "venue": {"fullName": "Arena"}}]}
    g = parse_event(event)
    assert g["game_id"] == "401" and g["is_completed"] is True
    assert g["home_team_id"] == "1" and g["away_score"] == 104


# --- storage -------------------------------------------------------------------------

def test_tables_are_created_per_sport_without_collision(tmp_path):
    db = tmp_path / "t.db"
    with sqlite3.connect(db) as conn:
        for key in ("nba", "nhl"):
            ensure_tables(conn, SPORTS[key])
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"nba_espn_player_logs", "nhl_espn_player_logs",
            "nba_espn_games", "nhl_espn_games"} <= names


def test_incremental_skip_keys_on_player_rows_not_the_games_table(tmp_path):
    """A game whose schedule row was written but whose box score failed must be retried,
    not skipped forever. Keying the skip on the logs table is what guarantees that."""
    from src.espn_boxscore import _stored_game_ids
    db = tmp_path / "t.db"
    with sqlite3.connect(db) as conn:
        ensure_tables(conn, SPORTS["nba"])
        conn.execute("INSERT INTO nba_espn_games (game_id) VALUES ('orphan')")
        assert _stored_game_ids(conn, SPORTS["nba"]) == set()
        conn.execute("INSERT INTO nba_espn_player_logs (game_id, player_id) "
                     "VALUES ('real', 'p1')")
        assert _stored_game_ids(conn, SPORTS["nba"]) == {"real"}


def test_collect_rejects_an_unknown_sport():
    from src.espn_boxscore import CollectorError
    with pytest.raises(CollectorError, match="Unknown sport"):
        collect("cricket", date(2026, 1, 1), date(2026, 1, 1))


def test_game_date_is_the_local_calendar_day_not_the_utc_instant():
    """ESPN dates are UTC instants: a 7pm ET tip on 9 Jan is '2026-01-10T00:00Z'. Storing
    that as `game_date` makes every `WHERE game_date = ...` silently wrong — it cost a
    validation run that reported 24% agreement with our vendor feed until the shift was
    found, then 99.1%. Both are kept: `start_time` is the instant, `game_date` the day."""
    event = {"id": "1", "date": "2026-01-10T00:00Z", "season": {"year": 2025, "type": 2},
             "status": {"type": {"completed": True}},
             "competitions": [{"competitors": [
                 {"homeAway": "home", "team": {"id": "1"}, "score": "1"},
                 {"homeAway": "away", "team": {"id": "2"}, "score": "0"}]}]}
    g = parse_event(event)
    assert g["game_date"] == "2026-01-09", "midnight UTC is the previous evening in ET"
    assert g["start_time"] == "2026-01-10T00:00Z"


def test_an_afternoon_game_keeps_its_own_date():
    event = {"id": "2", "date": "2026-01-10T18:00Z", "season": {"year": 2025, "type": 2},
             "status": {"type": {"completed": True}},
             "competitions": [{"competitors": [
                 {"homeAway": "home", "team": {"id": "1"}, "score": "1"},
                 {"homeAway": "away", "team": {"id": "2"}, "score": "0"}]}]}
    assert parse_event(event)["game_date"] == "2026-01-10"


def test_hockey_shots_on_goal_comes_from_S_not_the_dead_SOG_column():
    """ESPN's NHL box score carries both `S` and `SOG`. **`SOG` is always 0**; the real
    data is in `S`. Mapping them the obvious way round gave every one of 1,548 skaters a
    shots-on-goal of zero while the true values sat under a column named `shots` — caught
    only because a team SOG of 0.0 per game is impossible (the real figure was 26.7, and
    NHL averages ~30). Shots on goal is the headline NHL prop, so this must not regress."""
    payload = _payload(["TOI", "G", "A", "S", "SM", "SOG"],
                       [_athlete("1", "Skater", ["18:04", "1", "2", "4", "1", "0"])],
                       "forwards")
    row = parse_player_rows(payload, _GAME, SPORTS["nhl"])[0]
    assert row["shots_on_goal"] == 4.0, "S is the real shots-on-goal stat"
    assert row["shots_missed"] == 1.0
    assert "shots" not in row, "no second column may shadow shots_on_goal"
    assert "_espn_sog_unused" not in row


@pytest.mark.parametrize("key", sorted(SPORTS))
def test_every_declared_column_can_actually_be_populated(key):
    """A column in `columns` with no alias pointing at it is silently always-null — the
    table looks right and the data never arrives. This caught a real slip: an edit fixing
    the shots-on-goal mapping dropped `g -> goals` and `a -> assists`, and the only visible
    symptom was a `None` in a debug print that was mistaken for a formatting artifact."""
    spec = SPORTS[key]
    reachable = set(spec.stat_aliases.values())
    orphans = [c for c in spec.columns if c not in reachable]
    assert not orphans, f"{key}: no alias maps to {orphans}"


@pytest.mark.parametrize("key", sorted(SPORTS))
def test_split_and_clock_names_are_real_columns(key):
    spec = SPORTS[key]
    assert set(spec.splits) <= set(spec.columns)
    assert set(spec.clock) <= set(spec.columns)
