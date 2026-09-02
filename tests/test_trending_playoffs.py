from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from services import mlb_playoffs, mlb_trending
from services.standings import TeamStanding


def _standing(team_id, name, conference, division, rank, wins, losses):
    return TeamStanding(team_id=str(team_id), team_name=name, division=division,
                        division_rank=rank, wins=wins, losses=losses, ties=0,
                        games_behind=0, streak="W1", last_ten="6-4",
                        win_pct=wins / (wins + losses), conference=conference)


def test_the_division_race_and_the_wild_card_race_are_kept_apart():
    """They are two different questions and the page used to answer only one.

    Winning a division is a contest against four named clubs that ends in an automatic
    place. The Wild Card is a separate contest among everyone who does not win one. A
    combined six-team table showed a club's Wild Card standing and said nothing about
    the division race it was actually in.
    """
    teams = {}
    for league in ("American League", "National League"):
        prefix = "A" if league.startswith("American") else "N"
        for division_index, division in enumerate(("East", "Central", "West")):
            for rank in range(1, 6):
                wins = 90 - division_index * 2 - rank * 3
                team = _standing(f"{prefix}{division_index}{rank}",
                                 f"{prefix} Team {division_index}-{rank}", league,
                                 f"{league} {division}", rank, wins, 138 - wins)
                teams[team.team_id] = team
    panels, status = mlb_playoffs._race_rows(teams)

    assert len(panels) == 2
    for panel in panels:
        # Three division races, each with every club in it and the leader first.
        assert len(panel["divisions"]) == 3
        for division in panel["divisions"]:
            assert len(division["teams"]) == 5
            assert division["teams"][0]["status"] == "Leads the division"
            assert division["teams"][1]["status"].endswith("GB in the division")
        # The Wild Card race is only clubs that lead no division.
        assert len(panel["field"]) == 3
        assert [row["status"] for row in panel["field"]] == [
            "Wild Card 1", "Wild Card 2", "Wild Card 3"]

    # Division leaders are in the field and are never listed as Wild Cards.
    leaders = {d["teams"][0]["id"] for p in panels for d in p["divisions"]}
    wildcards = {r["id"] for p in panels for r in p["field"]}
    assert leaders and not (leaders & wildcards)
    assert all(status[tid]["in_field"] for tid in leaders | wildcards)


def test_a_club_can_be_live_in_both_races_at_once():
    """The case that made the combined table wrong: second in its division *and* holding
    a Wild Card. It has to appear in both, because it is genuinely racing in both."""
    teams = {}
    # East: a runaway leader and a strong second.
    for tid, name, rank, wins in (("E1", "Leader", 1, 95), ("E2", "Chaser", 2, 88)):
        teams[tid] = _standing(tid, name, "American League", "American League East",
                               rank, wins, 138 - wins)
    # Two weaker divisions, so the East runner-up clearly holds a Wild Card.
    for div, tid, wins in (("Central", "C1", 74), ("West", "W1", 72)):
        teams[tid] = _standing(tid, f"{div} Leader", "American League",
                               f"American League {div}", 1, wins, 138 - wins)
    panels, status = mlb_playoffs._race_rows(teams)
    east = next(d for d in panels[0]["divisions"] if d["name"].endswith("East"))

    assert [r["id"] for r in east["teams"]] == ["E1", "E2"]
    assert east["teams"][1]["status"].endswith("GB in the division")
    assert "E2" in {r["id"] for r in panels[0]["field"]}
    assert status["E2"]["in_field"] is True


def test_important_games_prefer_a_direct_division_race():
    status = {
        "1": {"conference": "American League", "division": "American League East",
              "gap": 0, "status": "Division leader", "in_field": True},
        "2": {"conference": "American League", "division": "American League East",
              "gap": 2, "status": "2 GB of Wild Card", "in_field": False},
    }
    games = [{"phase": "regular", "state": "pre", "away_id": 1, "home_id": 2,
              "away_short": "Rays", "home_short": "Yankees", "away_logo": None,
              "home_logo": None, "game_pk": 99, "game_date": "2026-09-05T23:05:00Z"}]
    result = mlb_playoffs._important_games(games, status)
    assert result[0]["game_id"] == 99
    assert "Direct AL East race" in result[0]["why"]


def test_inactive_batters_never_appear_as_trending():
    rows = []
    for pid, name, end in (("active", "Active Player", date(2026, 8, 31)),
                           ("stale", "Stale Player", date(2026, 7, 1))):
        for game in range(24):
            game_date = end - timedelta(days=23 - game)
            rows.append({"batter_id": pid, "batter_name": name, "batting_team": "Team",
                         "game_date": pd.Timestamp(game_date), "game_id": f"{pid}-{game}",
                         "is_hit": 1 if game >= 14 else 0, "is_strikeout": game % 3 == 0})
    cards = mlb_trending._batter_cards(pd.DataFrame(rows))
    names = {card["name"] for group in cards.values() for card in group}
    assert "Active Player" in names
    assert "Stale Player" not in names


def test_new_pages_are_public_static_export_seeds():
    from web.management.commands.export_static import _SEEDS

    assert "/trending/" in _SEEDS
    assert "/playoffs/" in _SEEDS


# --- Remaining games against the rest of the race -------------------------------------

def test_rival_meetings_counts_only_games_between_teams_in_the_race():
    """"Games left" does not say who they are against, and 24 against the field is a
    different September from 24 against the basement. Only games where *both* sides sit
    in the same conference's field-or-bubble count."""
    from services.mlb_playoffs import _rival_meetings

    status = {
        "1": {"conference": "AL", "division": "AL East", "gap": 0.0, "status": "x", "in_field": True},
        "2": {"conference": "AL", "division": "AL West", "gap": 1.0, "status": "x", "in_field": False},
        "3": {"conference": "NL", "division": "NL East", "gap": 0.0, "status": "x", "in_field": True},
    }
    games = [
        {"phase": "regular", "state": "pre", "away_id": "1", "home_id": "2"},    # counts
        {"phase": "regular", "state": "pre", "away_id": "1", "home_id": "3"},    # cross-conference
        {"phase": "regular", "state": "pre", "away_id": "1", "home_id": "99"},   # not in the race
        {"phase": "regular", "state": "final", "away_id": "1", "home_id": "2"},  # already played
        {"phase": "postseason", "state": "pre", "away_id": "1", "home_id": "2"},
    ]
    counts = _rival_meetings(games, status)
    assert counts["1"] == 1 and counts["2"] == 1
    assert counts["3"] == 0


def test_the_head_to_head_window_runs_past_the_two_week_view():
    """The fortnight bounds the *judgment* ("these games matter"), which is a claim about
    standings that have not happened yet. The head-to-head count is arithmetic over the
    whole run-in, so it must not be clipped to the same fortnight."""
    from datetime import date

    from services import mlb_playoffs

    asked = {}

    def _fetch(start, end):
        asked["start"], asked["end"] = start, end
        return []

    today = date(2026, 9, 1)
    mlb_playoffs.build_context(today, schedule_fetcher=_fetch)
    assert (asked["end"] - today).days > 14


# --- WNBA trending --------------------------------------------------------------------

def _wnba_db(tmp_path, rows):
    import sqlite3
    db = tmp_path / "w.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE wnba_player_game_logs (
        game_id TEXT, player_id TEXT, game_date TEXT, player_name TEXT, team TEXT,
        headshot TEXT, minutes REAL, points REAL, rebounds REAL, assists REAL)""")
    conn.executemany(
        "INSERT INTO wnba_player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return db


def _logs(pid, name, values, *, minutes=28.0, ending="2026-08-31", stat="points",
          offset=0):
    """One row per game, dated backwards from ``ending`` so the run is *recent*.

    Dating them from the start of the month instead put the last game weeks before the
    slate, and the recency filter correctly dropped the player — which is a fine rule
    and a poor fixture.
    """
    from datetime import date as _d
    from datetime import timedelta as _td

    end = _d.fromisoformat(ending) - _td(days=offset)
    out = []
    for i, v in enumerate(values):
        day = end - _td(days=(len(values) - 1 - i))
        pts = v if stat == "points" else 0
        reb = v if stat == "rebounds" else 0
        ast = v if stat == "assists" else 0
        out.append((f"g{pid}{day.isoformat()}", pid, f"{day.isoformat()}T00:30Z", name,
                    "Team", "h.png", minutes, pts, reb, ast))
    return out


def test_wnba_trending_finds_a_real_move(tmp_path):
    from datetime import date

    from services.wnba_trending import build_context

    rows = _logs("1", "Riser", [8] * 10 + [20] * 5)      # +12 a game
    ctx = build_context(date(2026, 9, 1), db_path=_wnba_db(tmp_path, rows))
    scoring = next(s for s in ctx["sections"] if s["slug"] == "points")
    assert scoring["cards"] and scoring["cards"][0]["tone"] == "up"
    assert "Riser" == scoring["cards"][0]["name"]


def test_a_quiet_change_is_not_a_trend(tmp_path):
    """Thresholds are per market — three assists is a transformation, three points is a
    quiet night — so a small move must not surface as one."""
    from datetime import date

    from services.wnba_trending import build_context

    rows = _logs("1", "Steady", [12] * 10 + [13] * 5)     # +1 a game
    ctx = build_context(date(2026, 9, 1), db_path=_wnba_db(tmp_path, rows))
    assert all(not s["cards"] for s in ctx["sections"])


def test_a_did_not_play_row_does_not_manufacture_a_slump(tmp_path):
    """A logged row with no minutes is a player who never took the floor. Counting it
    as a zero would invent a collapse out of a healthy scratch."""
    from datetime import date

    from services.wnba_trending import build_context

    rows = _logs("1", "Rested", [20] * 10, offset=5) + _logs(
        "1", "Rested", [0] * 5, minutes=0.0)
    ctx = build_context(date(2026, 9, 1), db_path=_wnba_db(tmp_path, rows))
    assert all(not s["cards"] for s in ctx["sections"])


def test_an_inactive_player_drops_off(tmp_path):
    """A leaderboard of players who stopped playing is a list of injuries."""
    from datetime import date

    from services.wnba_trending import build_context

    rows = _logs("1", "Gone", [8] * 10 + [20] * 5, ending="2026-06-30")
    ctx = build_context(date(2026, 9, 1), db_path=_wnba_db(tmp_path, rows))
    assert all(not s["cards"] for s in ctx["sections"])


def test_wnba_mirrors_the_mlb_card_contract(tmp_path):
    """One template serves both pages, so the shapes must not drift apart."""
    from datetime import date

    from services.wnba_trending import build_context

    ctx = build_context(date(2026, 9, 1),
                        db_path=_wnba_db(tmp_path, _logs("1", "R", [8] * 10 + [20] * 5)))
    assert set(ctx) >= {"section", "league", "sections", "through", "has_data"}
    card = next(s for s in ctx["sections"] if s["cards"])["cards"][0]
    assert set(card) >= {"market", "icon", "player_id", "name", "team", "headshot",
                         "headline", "detail", "tone", "value"}


# --- When the playoff page is live, and when it stops being true ----------------------

def _fake_table(records, league="MLB"):
    from services.standings import TeamStanding
    return {str(i): TeamStanding(
        team_id=str(i), team_name=f"T{i}", division="D", division_rank=1,
        wins=w, losses=l, ties=0, games_behind=0, streak=None, last_ten=None)
        for i, (w, l) in enumerate(records)}


def test_the_window_opens_on_games_left_not_a_date():
    """A date breaks on a lockout or a shortened season and has to be re-derived per
    league. Games left is what actually decides whether a race is legible."""
    from services import playoff_window as W

    assert W.state("MLB", _fake_table([(60, 50)])) == "early"      # 52 left, July
    assert W.state("MLB", _fake_table([(80, 52)])) == "live"       # 30 left, late Aug
    assert W.state("NFL", _fake_table([(7, 3)])) == "early"        # 8 left, week 10
    assert W.state("NFL", _fake_table([(8, 4)])) == "live"         # 6 left, week 12


def test_the_thresholds_differ_because_leverage_does():
    """MLB opens at ~85% of the season played and the NFL at ~65%. That is leverage per
    game, not inconsistency: six football games make a two-game deficit close to fatal."""
    from services import playoff_window as W

    mlb_len, mlb_gate = W.LEAGUE_WINDOWS["MLB"]
    nfl_len, nfl_gate = W.LEAGUE_WINDOWS["NFL"]
    assert (mlb_len - mlb_gate) / mlb_len > (nfl_len - nfl_gate) / nfl_len


def test_a_finished_season_persists_but_is_worded_as_finished():
    """The race stays up through the offseason — how it ended is a real record — but it
    must not still say "if the season ended today" about a season that has."""
    from services import playoff_window as W

    assert W.state("MLB", _fake_table([(100, 62)])) == "final"
    eyebrow, disclaimer = W.headline("MLB", "final")
    assert "finished" in eyebrow.lower()
    assert "over" in disclaimer.lower()
    assert "if the season ended today" not in eyebrow.lower()


def test_the_new_season_is_the_off_switch():
    """Standings reset to 0-0 when the next season starts. Last year's race must not sit
    beside this year's schedule."""
    from services import playoff_window as W

    assert W.state("MLB", _fake_table([(0, 0), (0, 0)])) == "preseason"
    assert W.state("MLB", {}) == "preseason"


def test_a_team_with_games_in_hand_cannot_hold_the_page_open():
    """The gate reads the *fewest* games any club has left. Taking the maximum would keep
    a resolved race live on one rained-out team."""
    from services import playoff_window as W

    assert W.state("MLB", _fake_table([(100, 62), (95, 60)])) == "live"


def test_an_out_of_window_page_renders_nothing_rather_than_a_stale_race():
    from datetime import date

    from services import mlb_playoffs

    ctx = mlb_playoffs.build_context(
        date(2026, 5, 1), schedule_fetcher=lambda a, b: [])
    assert ctx["has_data"] is False and ctx["panels"] == []


def test_the_wnba_field_is_one_table_of_eight_not_two_conferences():
    """The WNBA has seeded 1-8 across the whole league since 2016 — no divisions, no
    conference split, no automatic bids. Forcing it through the MLB shape would invent
    structure the league does not have."""
    from services import wnba_playoffs

    teams = {str(i): _standing(str(i), f"Team {i}", "WNBA", "WNBA", i, 30 - i, 10 + i)
             for i in range(1, 13)}
    panels, status = wnba_playoffs.race(teams)

    assert len(panels) == 1
    assert len(panels[0]["field"]) == 8
    assert [r["seed"] for r in panels[0]["field"]] == list(range(1, 9))
    assert panels[0]["field"][0]["status"] == "Top-four seed"
    assert panels[0]["field"][4]["status"] == "In the field"
    assert sum(1 for s in status.values() if s["in_field"]) == 8


def test_an_empty_chasing_list_says_which_kind_of_empty_it_is():
    """"Nobody is close" and "everybody left is mathematically out" look identical as an
    empty list. With four games to play and the ninth club eight back, the field is set
    and the page should say so rather than show a blank section."""
    from services import wnba_playoffs

    teams = {}
    for i in range(1, 9):
        teams[str(i)] = _standing(str(i), f"In {i}", "WNBA", "WNBA", i, 24, 16)
    # Ninth is far enough back that it cannot catch up in the games that remain.
    teams["9"] = _standing("9", "Out", "WNBA", "WNBA", 9, 16, 24)
    panel = wnba_playoffs.race(teams)[0][0]

    assert panel["bubble"] == []
    assert panel["decided"] is True
    assert "field is set" in panel["note"]
