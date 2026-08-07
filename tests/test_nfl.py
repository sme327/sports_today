"""NFL schedule-only adapter: parsing, schedule-only contract, compact card."""

from __future__ import annotations

from datetime import date

import leagues  # noqa: F401  (register adapters)
from components.game_cards import game_card_html
from leagues.base import get_adapter
from src.nfl_api import _parse_nfl, _round_label

# A trimmed ESPN NFL scoreboard payload (preseason).
_PAYLOAD = {
    "events": [{
        "id": "401700001",
        "date": "2026-08-15T17:00Z",
        "season": {"year": 2026, "type": 1, "slug": "preseason"},
        "week": {"number": 2},
        "status": {"type": {"state": "pre", "detail": "Sat, Aug 15",
                            "shortDetail": "8/15 - 1:00 PM ET", "description": "Scheduled"}},
        "competitions": [{
            "venue": {"fullName": "Highmark Stadium"},
            "broadcasts": [{"names": ["NFL Network"]}],
            "competitors": [
                {"homeAway": "home", "score": "0",
                 "team": {"displayName": "Buffalo Bills", "shortDisplayName": "Bills",
                          "abbreviation": "BUF", "logos": [{"href": "http://x/buf.png"}]}},
                {"homeAway": "away", "score": "0",
                 "team": {"displayName": "Carolina Panthers", "shortDisplayName": "Panthers",
                          "abbreviation": "CAR", "logo": "http://x/car.png"}},
            ],
        }],
    }]
}


def test_parse_extracts_matchup_and_preseason_label():
    games = _parse_nfl(_PAYLOAD)
    assert len(games) == 1
    g = games[0]
    assert g["home"] == "Buffalo Bills" and g["away"] == "Carolina Panthers"
    assert g["round"] == "Preseason · Wk 2"
    assert g["state"] == "pre"
    assert g["away_logo"] == "http://x/car.png"       # falls back to team.logo when no logos[]
    assert g["venue"] == "Highmark Stadium"


def test_round_label_variants():
    assert _round_label({"season": {"type": 2}, "week": {"number": 5}}) == "Regular Season · Wk 5"
    assert _round_label({"season": {"slug": "postseason"}}) == "Postseason"
    assert _round_label({}) == "NFL"


def test_adapter_is_schedule_only():
    nfl = get_adapter("NFL")
    assert nfl is not None
    assert nfl.supports_deep_dive is False
    assert nfl.opportunities(as_of=date(2026, 8, 15)) == []


def test_adapter_builds_slate_games_and_compact_card(monkeypatch):
    nfl = get_adapter("NFL")
    monkeypatch.setattr("leagues.nfl.adapter.nfl_schedule", lambda d: _parse_nfl(_PAYLOAD))
    games = nfl.fetch_schedule(date(2026, 8, 15))
    assert len(games) == 1 and games[0].league == "NFL"
    html = game_card_html(games[0], "today")
    assert "game-card--compact" in html    # schedule-only → compact
    assert "game-meta" not in html          # no fire/matchup footer
    assert "game-time" in html
