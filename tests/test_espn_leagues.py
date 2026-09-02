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


def test_all_four_leagues_registered_and_carry_no_props():
    """All four are ESPN schedule-only for *props* — that is the invariant here, and it
    still holds. Every one now offers a matchup page, but conditionally: NFL where its
    season feed covers the game, the rest where the records are old enough to read."""
    for lg in ("NFL", "NHL", "NBA", "NCAAF"):
        a = get_adapter(lg)
        assert a is not None, lg
        assert a.opportunities(as_of=date(2026, 8, 30)) == []
        assert a.supports_deep_dive is True
        assert callable(getattr(a, "deep_dive_available", None)), (
            f"{lg} must decide per game, so a card stays compact with nothing to say")


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


# --- ESPN group/limit handling (2026-08-11) ----------------------------------------

def test_fetch_unions_groups_and_deduplicates(monkeypatch):
    """ESPN splits college sports across divisions, and a response is truncated per
    request. Fetching several groups and unioning by id is the only way to see a full
    college slate — measured on NCAAF, where FBS and FCS returned 45 and 56 games with an
    overlap of 2."""
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params.get("groups"))
        gid = f"g{params.get('groups')}"
        class R:
            @staticmethod
            def raise_for_status(): pass
            @staticmethod
            def json():
                return {"events": [{"id": gid}, {"id": "shared"}]}
        return R()

    monkeypatch.setattr("src.espn_scoreboard.requests.get", fake_get)
    monkeypatch.setattr("src.espn_scoreboard.parse_events",
                        lambda payload: [{"game_id": e["id"]} for e in payload["events"]])
    out = sb.fetch("x/y", date(2026, 1, 10), groups=(80, 81))
    assert calls == [80, 81]
    ids = {g["game_id"] for g in out}
    assert ids == {"g80", "g81", "shared"}, "the shared game must appear once, not twice"


def test_one_failing_group_does_not_lose_the_others(monkeypatch):
    """A partial slate beats an empty one, but only if the working groups survive."""
    def fake_get(url, params=None, timeout=None):
        if params.get("groups") == 80:
            raise RuntimeError("ESPN hiccup")
        class R:
            @staticmethod
            def raise_for_status(): pass
            @staticmethod
            def json(): return {"events": [{"id": "kept"}]}
        return R()

    monkeypatch.setattr("src.espn_scoreboard.requests.get", fake_get)
    monkeypatch.setattr("src.espn_scoreboard.parse_events",
                        lambda payload: [{"game_id": e["id"]} for e in payload["events"]])
    out = sb.fetch("x/y", date(2026, 1, 10), groups=(80, 81))
    assert [g["game_id"] for g in out] == ["kept"]


def test_total_failure_still_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr("src.espn_scoreboard.requests.get", boom)
    assert sb.fetch("x/y", date(2026, 1, 10), groups=(80, 81)) == []


def test_adapters_declare_their_group_and_limit_needs():
    """Fixed adapter config stays narrow; NCAAF widens only during August Week Zero."""
    for lg in ("NFL", "NBA", "NHL", "NCAAF"):
        a = get_adapter(lg)
        assert getattr(a, "espn_groups", ()) == (), f"{lg} should not need groups"
        assert getattr(a, "espn_limit", 100) == 100

    ncaaf = get_adapter("NCAAF")
    assert ncaaf.scoreboard_groups(date(2026, 8, 27)) == (80, 81)
    assert ncaaf.scoreboard_groups(date(2026, 9, 3)) == ()


def test_ncaaf_passes_week_zero_groups_to_the_scoreboard(monkeypatch):
    calls = []

    def fake_fetch(path, d, **kwargs):
        calls.append(kwargs.get("groups"))
        return []

    monkeypatch.setattr("src.espn_scoreboard.fetch", fake_fetch)
    adapter = get_adapter("NCAAF")
    adapter.fetch_schedule(date(2026, 8, 27))
    adapter.fetch_schedule(date(2026, 9, 3))
    assert calls == [(80, 81), None]


def test_ncaaf_week_zero_offers_the_simplified_matchup_dry_run():
    from datetime import datetime, timezone
    from domain.models import SlateGame

    adapter = get_adapter("NCAAF")
    week_zero = SlateGame(league="NCAAF", game_id="1",
                          start_time=datetime(2026, 8, 27, 22, tzinfo=timezone.utc),
                          away_name="Maine", home_name="Towson")
    assert adapter.deep_dive_available(week_zero) is True

    week_one = SlateGame(league="NCAAF", game_id="2",
                         start_time=datetime(2026, 9, 3, 22, tzinfo=timezone.utc),
                         away_name="A", home_name="B", away_record="0-0", home_record="0-0")
    assert adapter.deep_dive_available(week_one) is False


def test_the_market_line_survives_the_adapter():
    """The parser captured it and the adapter dropped it.

    `_espn_schedule` builds its own `meta` rather than passing the parsed row through, so
    a new field is only present if it is copied by name. The line was parsed correctly,
    published, and rendered nowhere — the failure looked like an odds problem and was a
    plumbing one, one layer above where the field was added.
    """
    from datetime import date
    from unittest.mock import patch

    from leagues.base import get_adapter

    row = {
        "game_id": "1", "game_date": "2026-09-03T23:00Z", "away": "Colorado",
        "home": "Georgia Tech", "away_short": "Colorado", "home_short": "Georgia Tech",
        "market_line": {"detail": "GT -6.5", "spread": -6.5, "total": 51.5,
                        "favourite": "GT", "provider": "Draft Kings"},
    }
    with patch("src.espn_scoreboard.fetch", return_value=[row]):
        games = get_adapter("NCAAF").fetch_schedule(date(2026, 9, 3))

    assert games[0].meta["market_line"]["detail"] == "GT -6.5"
    assert games[0].meta["market_line"]["total"] == 51.5


def test_a_game_without_a_line_carries_none_rather_than_an_empty_shape():
    """Most sports and most days have no line. Absent must be absent, so the page can
    simply not render the section rather than showing an empty one."""
    from datetime import date
    from unittest.mock import patch

    from leagues.base import get_adapter

    with patch("src.espn_scoreboard.fetch",
               return_value=[{"game_id": "1", "game_date": "2026-09-03T23:00Z",
                              "away": "A", "home": "B"}]):
        games = get_adapter("NCAAF").fetch_schedule(date(2026, 9, 3))
    assert games[0].meta["market_line"] is None
