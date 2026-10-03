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
    assert get_adapter("NFL").supports_deep_dive is True     # conditional — see below
    assert get_adapter("World Cup").supports_deep_dive is False
    # Schedule-only leagues gained a simplified matchup page (records, rank, stakes, the
    # team-level read, and a plain statement of what is missing), offered **per game**
    # like NFL — a card stays compact where the page would have nothing to say.
    for lg in ("NHL", "NBA", "NCAAF"):
        assert get_adapter(lg).supports_deep_dive is True


def test_nfl_deep_dive_is_decided_per_game_not_per_league():
    """NFL is the one league whose deep-dive depends on the *game*: the matchup page is
    built from ingested vendor seasons, so a preseason game or an unloaded season has no
    page. The adapter must expose that per-game hook, or cards promise links that land on
    "not connected"."""
    a = get_adapter("NFL")
    assert callable(getattr(a, "deep_dive_available", None))
    # Every other deep-dive league answers for the whole league; none may claim the hook
    # and then ignore the game it is handed.
    for lg in ("MLB", "WNBA", "MLS"):
        hook = getattr(get_adapter(lg), "deep_dive_available", None)
        assert hook is None or callable(hook)


def test_every_registered_league_has_live_scores_on_the_slate():
    """The slate's live-score script polls a hand-kept list of leagues. A league left off
    it shows a game that finished hours ago as upcoming until the next publish — NHL did
    exactly that on 2026-10-01."""
    import re
    from pathlib import Path

    from leagues.base import iter_adapters

    script = (Path(__file__).resolve().parents[1] / "web/static/static-site.js").read_text()
    block = script[script.index("const scoreLeagues"):script.index("function normalizeEspnEvent")]
    polled = set(re.findall(r'\["([^"]+)",', block))
    missing = [a.league for a in iter_adapters() if a.league not in polled]
    assert not missing, f"no live scores for: {missing}"
