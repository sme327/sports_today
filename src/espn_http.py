"""One place that decides which ESPN host to ask.

**Why two hosts.** `site.api.espn.com` sits behind a rule that answers 403 to many
non-curl User-Agents — browser-shaped strings and Cloudflare Worker fetches both — while
`site.web.api.espn.com` serves byte-identical JSON at the same paths and answered every
agent tried (tested 2026-09-13; the same day a browser-shaped agent on the old host broke
the first NFL grading run). Neither host is reliably better forever, so every client tries
the web host first and falls back to the original rather than picking one.

The failure this prevents is quiet and total: a 403 on the first request of a collector
looks exactly like a network blip, and a daily run that swallows collector errors turns it
into "no data today". KOTH does the same thing in `src/espn.ts`; `Projects/DATA-SOURCES.md`
is the shared note.

Use `espn_get` in place of `session.get` / `requests.get`, and `host_candidates` where a
client builds URLs itself (`urllib`, say). A URL on neither host is passed through
untouched, so this is safe to wrap around any call.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

WEB_HOST = "site.web.api.espn.com"
SITE_HOST = "site.api.espn.com"
# Ordered: the host that answered everything first, the original as the fallback.
HOSTS = (WEB_HOST, SITE_HOST)


def host_candidates(url: str) -> list[str]:
    """``url`` rewritten onto each ESPN host in order, or ``[url]`` when it is not an
    ESPN site-API URL (the core API and every other host are left alone)."""
    parts = urlsplit(url)
    if parts.netloc not in HOSTS:
        return [url]
    return [urlunsplit(parts._replace(netloc=host)) for host in HOSTS]


def espn_get(getter, url: str, **kwargs):
    """GET ``url``, trying each ESPN host in turn; the first non-error response wins.

    ``getter`` is anything with requests' ``get`` signature — a ``Session``'s bound
    ``get``, or ``requests.get`` itself. A response that is not ``ok`` is treated as a
    failure worth trying the next host for, which is the whole point: the 403 is a host
    property, not a request property. The last error is raised (or the last response
    returned) when every host fails, so callers keep whatever error handling they had.
    """
    candidates = host_candidates(url)
    last_response = None
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            response = getter(candidate, **kwargs)
        except Exception as exc:                       # noqa: BLE001 - retried, then re-raised
            last_error = exc
            continue
        if getattr(response, "ok", True):
            return response
        last_response = response
    if last_response is not None:
        return last_response                           # caller raises for status as before
    raise last_error                                   # type: ignore[misc]
