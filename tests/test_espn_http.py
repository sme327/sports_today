"""The ESPN host fallback: web host first, the original as the fallback, and anything
that is not an ESPN site-API URL left alone."""

from __future__ import annotations

import pytest

from src.espn_http import SITE_HOST, WEB_HOST, espn_get, host_candidates


class _Resp:
    def __init__(self, ok: bool, url: str, status: int = 200):
        self.ok, self.url, self.status_code = ok, url, status


def _fake(behaviour):
    """A getter that answers per-host from ``behaviour``: an int status, or an Exception."""
    seen: list[str] = []

    def get(url, **kwargs):
        seen.append(url)
        host = url.split("/")[2]
        outcome = behaviour[host]
        if isinstance(outcome, Exception):
            raise outcome
        return _Resp(outcome < 400, url, outcome)

    return get, seen


def test_web_host_is_tried_first_and_the_old_one_is_the_fallback():
    url = f"https://{SITE_HOST}/apis/site/v2/sports/football/nfl/scoreboard"
    assert host_candidates(url) == [
        f"https://{WEB_HOST}/apis/site/v2/sports/football/nfl/scoreboard",
        f"https://{SITE_HOST}/apis/site/v2/sports/football/nfl/scoreboard",
    ]
    # A URL already on the web host still lists both, in the same order.
    assert host_candidates(f"https://{WEB_HOST}/x") == [f"https://{WEB_HOST}/x",
                                                        f"https://{SITE_HOST}/x"]


def test_a_non_espn_url_is_passed_through_untouched():
    for url in ("https://sports.core.api.espn.com/v2/sports/football/leagues/nfl",
                "https://statsapi.mlb.com/api/v1/schedule",
                "http://example.test/x?y=1"):
        assert host_candidates(url) == [url]


def test_the_403_on_the_old_host_is_survived():
    """The failure this exists for: the old host 403s, the web host serves the JSON."""
    get, seen = _fake({WEB_HOST: 200, SITE_HOST: 403})
    r = espn_get(get, f"https://{SITE_HOST}/apis/site/v2/sports/x")
    assert r.ok and WEB_HOST in r.url and seen == [f"https://{WEB_HOST}/apis/site/v2/sports/x"]


def test_the_fallback_runs_when_the_web_host_fails():
    get, seen = _fake({WEB_HOST: 500, SITE_HOST: 200})
    r = espn_get(get, f"https://{SITE_HOST}/x")
    assert r.ok and SITE_HOST in r.url
    assert [u.split("/")[2] for u in seen] == [WEB_HOST, SITE_HOST]

    # A raised connection error is also a reason to try the next host.
    get, seen = _fake({WEB_HOST: ConnectionError("boom"), SITE_HOST: 200})
    assert espn_get(get, f"https://{SITE_HOST}/x").ok
    assert [u.split("/")[2] for u in seen] == [WEB_HOST, SITE_HOST]


def test_when_every_host_fails_the_caller_still_sees_the_failure():
    """Callers raise_for_status or check .ok themselves; the helper must not swallow."""
    get, _ = _fake({WEB_HOST: 403, SITE_HOST: 403})
    r = espn_get(get, f"https://{SITE_HOST}/x")
    assert r.ok is False and r.status_code == 403

    get, _ = _fake({WEB_HOST: ConnectionError("a"), SITE_HOST: ConnectionError("b")})
    with pytest.raises(ConnectionError):
        espn_get(get, f"https://{SITE_HOST}/x")


def test_keyword_arguments_reach_the_getter():
    captured = {}

    def get(url, **kwargs):
        captured.update(kwargs)
        return _Resp(True, url)

    espn_get(get, f"https://{SITE_HOST}/x", params={"dates": "20260913"}, timeout=15)
    assert captured == {"params": {"dates": "20260913"}, "timeout": 15}
