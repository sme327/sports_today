from __future__ import annotations

from datetime import date, datetime

from domain.models import DataStatus, Opportunity, OpportunityMode, SlateGame, SourceStatus
from services import daily_feed, schedule_cache


def _opportunity() -> Opportunity:
    return Opportunity(
        league="MLB",
        player_id="17",
        player_name="Test Player",
        team_id="SEA",
        team_name="Mariners",
        market="1+ Hit",
        market_key="batter_hit",
        direction="over",
        threshold=1,
        opportunity_score=91,
        stability_score=78,
        supporting_evidence=["Strong recent contact"],
        negative_evidence=["Limited sample"],
        recent_line=[0, 1, 2],
        line_threshold=1,
        image_url="https://example.com/team.png",
        headshot_url="https://example.com/player.png",
        game_id="g1",
        mode=OpportunityMode.SLATE,
        components={"form": 0.8},
        data_status=DataStatus("test", SourceStatus.CACHED, datetime(2026, 8, 15, 8)),
    )


def test_daily_feed_round_trip_is_lossless_for_display_fields(tmp_path):
    db = tmp_path / "sports.db"
    daily_feed.store(date(2026, 8, 15), [_opportunity()], db_path=db)
    loaded, calculated_at = daily_feed.load(date(2026, 8, 15), db_path=db)

    assert calculated_at is not None
    assert len(loaded) == 1
    actual = loaded[0]
    assert actual.player_name == "Test Player"
    assert actual.recent_line == [0, 1, 2]
    assert actual.line_cleared == [False, True, True]
    assert actual.headshot_url.endswith("player.png")
    assert actual.data_status.status is SourceStatus.CACHED


def test_every_league_with_a_registered_model_version_feeds_the_slate():
    """Registering a market (domain/markets.py + snapshots.MODEL_VERSIONS) is not enough
    on its own — the league must also be in daily_feed._ANALYSIS_LEAGUES or its props are
    never scored, snapshotted, or graded. NFL shipped in exactly that state (2026-08-19):
    five markets, a scorer, an adapter hook and a grading branch, with nothing calling the
    adapter. Invisible, because its preseason staleness gate returns [] anyway."""
    from domain.markets import MARKETS
    from services import snapshots

    unknown = {key for key in snapshots.MODEL_VERSIONS if key not in MARKETS}
    assert not unknown, f"MODEL_VERSIONS names markets missing from the registry: {sorted(unknown)}"
    needed = {MARKETS[key].league for key in snapshots.MODEL_VERSIONS}
    missing = needed - daily_feed._ANALYSIS_LEAGUES
    assert not missing, (
        f"{sorted(missing)} have model versions registered but are not in "
        f"daily_feed._ANALYSIS_LEAGUES, so their props never reach the slate or the ledger."
    )


class _StubNFLAdapter:
    """The smallest adapter build_opportunities needs: league, match_team, opportunities."""

    league = "NFL"
    source_name = "stub"

    def __init__(self, opportunity: Opportunity):
        self._opportunity = opportunity

    def match_team(self, identifier):
        token = "".join(ch for ch in str(identifier or "").upper() if ch.isalnum())
        return token or None

    def opportunities(self, *, as_of, scheduled_team_ids=None,
                      mode=OpportunityMode.SLATE, limit=8):
        return [self._opportunity]


def test_nfl_opportunities_reach_the_slate_feed(monkeypatch):
    """Behavioral half of the guard above: an NFL adapter's props actually come out of
    build_opportunities, stamped with the slate game they belong to."""
    prop = Opportunity(
        league="NFL", player_id="42", player_name="Stub Receiver", team_id=None,
        team_name="Philadelphia Eagles", market="4+ receptions",
        market_key="nfl_receptions", direction="over", threshold=4,
        opportunity_score=88, stability_score=70,
        supporting_evidence=[], negative_evidence=[], recent_line=[5, 6, 4],
        line_threshold=4, mode=OpportunityMode.SLATE, components={},
    )
    stub = _StubNFLAdapter(prop)
    monkeypatch.setattr(daily_feed, "get_adapter",
                        lambda league: stub if league == "NFL" else None)
    game = SlateGame(league="NFL", game_id="401772980",
                     away_name="Dallas Cowboys", home_name="Philadelphia Eagles",
                     home_logo="https://example.com/phi.png")
    slates = {"NFL": ([game], DataStatus("stub", SourceStatus.LIVE, datetime(2026, 9, 13, 8)))}

    out = daily_feed.build_opportunities(date(2026, 9, 13), slates)

    assert [o.player_name for o in out] == ["Stub Receiver"]
    assert out[0].game_id == "401772980"          # _stamp joined it to its slate game
    assert out[0].image_url == "https://example.com/phi.png"


def test_cached_schedule_reader_includes_legitimate_empty_slates(tmp_path):
    db = tmp_path / "sports.db"
    fetched = datetime(2026, 8, 15, 7, 30)
    schedule_cache.write(
        league="MLB",
        slate_date=date(2026, 8, 15),
        source="MLB StatsAPI",
        status=SourceStatus.EMPTY,
        games=[],
        fetched_at=fetched,
        db_path=db,
    )
    cached = schedule_cache.read_latest(
        league="MLB", slate_date=date(2026, 8, 15), db_path=db
    )
    assert cached is not None
    games, status, actual_fetched, source = cached
    assert games == []
    assert status is SourceStatus.EMPTY
    assert actual_fetched == fetched
    assert source == "MLB StatsAPI"
