import leagues  # noqa: F401  (registers adapters on import)
from leagues.base import LeagueAdapter, get_adapter, iter_adapters


def test_all_leagues_registered_in_order():
    assert [a.league for a in iter_adapters()] == [
        "MLB", "WNBA", "NBA", "World Cup", "MLS", "NFL", "NCAAF", "NHL"]


def test_adapters_satisfy_protocol():
    for adapter in iter_adapters():
        assert isinstance(adapter, LeagueAdapter)
        assert adapter.label and adapter.emoji and adapter.source_name


def test_deep_dive_support_flags():
    assert get_adapter("MLB").supports_deep_dive is True
    assert get_adapter("WNBA").supports_deep_dive is True   # WNBA matchup page shipped
    assert get_adapter("MLS").supports_deep_dive is True     # MLS matchup page shipped
    assert get_adapter("World Cup").supports_deep_dive is False
    for lg in ("NFL", "NHL", "NBA", "NCAAF"):                 # schedule-only (ESPN)
        assert get_adapter(lg).supports_deep_dive is False
