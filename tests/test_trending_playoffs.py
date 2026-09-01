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


def test_playoff_picture_has_six_teams_per_league_and_a_wild_card_line():
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
    panels, _ = mlb_playoffs._race_rows(teams)
    assert [len(panel["field"]) for panel in panels] == [6, 6]
    assert all(panel["field"][0]["status"] == "Division leader" for panel in panels)
    assert all(panel["field"][3]["status"] == "Wild Card 1" for panel in panels)


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
