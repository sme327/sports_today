"""Shared ESPN scoreboard client + the schedule-only leagues it feeds
(NFL, NHL, NBA, NCAA Football): parsing, round labels, ranks, and the
schedule-only contract."""

from __future__ import annotations

from datetime import date

import leagues  # noqa: F401  (register adapters)
from components.game_cards import game_card_html
from leagues.base import get_adapter
from src import espn_scoreboard as sb

# A trimmed ESPN scoreboard payload: one ranked, neutral-site football game.
_PAYLOAD = {
    "events": [{
        "id": "401700001",
        "date": "2026-08-30T23:00Z",
        "season": {"year": 2026, "type": 1, "slug": "preseason"},
        "week": {"number": 2},
        "status": {"type": {"state": "pre", "detail": "Sat, Aug 30",
                            "shortDetail": "8/30 - 7:00 PM ET", "description": "Scheduled"}},
        "competitions": [{
            "venue": {"fullName": "Mercedes-Benz Stadium"},
            "neutralSite": True,
            "broadcasts": [{"names": ["ABC"]}],
            "competitors": [
                {"homeAway": "home", "score": "0", "curatedRank": {"current": 99},
                 "team": {"displayName": "Clemson Tigers", "shortDisplayName": "Clemson",
                          "abbreviation": "CLEM", "logos": [{"href": "http://x/clem.png"}]}},
                {"homeAway": "away", "score": "0", "curatedRank": {"current": 5},
                 "team": {"displayName": "Georgia Bulldogs", "shortDisplayName": "Georgia",
                          "abbreviation": "UGA", "logo": "http://x/uga.png"}},
            ],
        }],
    }]
}


def test_parse_extracts_matchup_rank_and_logos():
    g = sb.parse_events(_PAYLOAD)[0]
    assert g["home"] == "Clemson Tigers" and g["away"] == "Georgia Bulldogs"
    assert g["away_rank"] == 5 and g["home_rank"] is None      # 99 → unranked
    assert g["away_logo"] == "http://x/uga.png"                # falls back to team.logo
    assert g["state"] == "pre" and g["neutral_site"] is True
    assert g["season_type"] == 1 and g["week"] == 2


def test_round_label_variants():
    g = sb.parse_events(_PAYLOAD)[0]
    assert sb.round_label(g, with_week=True) == "Preseason · Wk 2"
    assert sb.round_label({"season_type": 2, "week": 5}, with_week=True) == "Regular Season · Wk 5"
    assert sb.round_label({"season_slug": "postseason"}) == "Postseason"
    assert sb.round_label({}) == ""


def test_all_four_leagues_registered_and_schedule_only():
    for lg in ("NFL", "NHL", "NBA", "NCAAF"):
        a = get_adapter(lg)
        assert a is not None, lg
        assert a.supports_deep_dive is False
        assert a.opportunities(as_of=date(2026, 8, 30)) == []


def test_ncaaf_prefixes_rank_and_builds_compact_card(monkeypatch):
    monkeypatch.setattr("src.espn_scoreboard.fetch", lambda path, d, **k: sb.parse_events(_PAYLOAD))
    games = get_adapter("NCAAF").fetch_schedule(date(2026, 8, 30))
    assert len(games) == 1
    g = games[0]
    assert g.away_display == "#5 Georgia"          # ranked prefix
    assert g.home_display == "Clemson"             # unranked, no prefix
    assert g.meta["round"] == "Preseason · Wk 2" and g.meta["neutral_site"] is True
    html = game_card_html(g, "today")
    # A ranked side is worth saying, so this card earns a footer chip. Schedule-only
    # cards stay compact only when there is genuinely nothing to say — see below.
    assert "ed-card-signal" in html and "#5 in action" in html


def test_schedule_only_card_stays_compact_when_there_is_nothing_to_say(monkeypatch):
    """The 2026-08-07 decision made these cards compact because a schedule-only game
    had no analysis to show. Editorial signals changed that premise *only* where a
    signal exists; an unranked game with no records must still render short."""
    payload = {"events": [{
        "id": "1", "date": "2026-08-30T23:00Z",
        "season": {"year": 2026, "type": 2, "slug": "regular-season"},
        "status": {"type": {"state": "pre", "detail": "Sat", "shortDetail": "8/30"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"displayName": "Home Town", "shortDisplayName": "Home"}},
            {"homeAway": "away", "team": {"displayName": "Away City", "shortDisplayName": "Away"}},
        ]}],
    }]}
    monkeypatch.setattr("src.espn_scoreboard.fetch", lambda path, d, **k: sb.parse_events(payload))
    g = get_adapter("NHL").fetch_schedule(date(2026, 8, 30))[0]
    html = game_card_html(g, "today")
    assert "game-card--compact" in html and "game-meta" not in html


def test_nfl_and_nhl_map_league_and_round(monkeypatch):
    monkeypatch.setattr("src.espn_scoreboard.fetch", lambda path, d, **k: sb.parse_events(_PAYLOAD))
    nfl = get_adapter("NFL").fetch_schedule(date(2026, 8, 30))[0]
    assert nfl.league == "NFL" and nfl.meta["round"] == "Preseason · Wk 2"
    assert nfl.away_display == "Georgia"           # NFL doesn't prefix ranks
    nhl = get_adapter("NHL").fetch_schedule(date(2026, 8, 30))[0]
    assert nhl.league == "NHL" and nhl.meta["round"] == "Preseason"   # no week for hockey
