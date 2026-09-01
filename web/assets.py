"""Cache-busting asset URLs (stylesheets and the script), derived from the files
rather than remembered.

The stylesheets were versioned by a hand-typed query string (`?v=20260817-2`). It failed
the way hand-maintained versions always do: a header rewrite landed entirely in
`web.css`, only `app.css`'s string was bumped, and the published page kept serving a
two-day-old stylesheet. The change was committed, pushed and deployed, and invisible.

The version is now the first 10 hex of the file's SHA-256, so it changes exactly when the
file does and never when it doesn't. Cached in production because the files cannot change
under a running process; recomputed every call under DEBUG so editing CSS during
development does not need a restart.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from django.conf import settings


def _find(name: str) -> Path | None:
    for root in settings.STATICFILES_DIRS:
        candidate = Path(root) / name
        if candidate.exists():
            return candidate
    return None


def _digest(name: str) -> str:
    path = _find(name)
    if path is None:
        return "0"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


@lru_cache(maxsize=8)
def _cached_digest(name: str) -> str:
    return _digest(name)


def stylesheet_version(name: str) -> str:
    return _digest(name) if settings.DEBUG else _cached_digest(name)


def build_stamp() -> str:
    """Today's feed's calculated_at, for the page's build-stamp meta tag.

    The publish check compares this between the built page and the live origin. The
    stylesheet-hash check only proves the CSS deployed — after a pure *data* update
    the CSS is unchanged, so a half-failed HTML upload would pass it while the site
    served yesterday's slate. Empty when no feed exists (fresh install); the check
    skips rather than guesses.
    """
    from django.core.cache import cache

    cached = cache.get("build-stamp")
    if cached is not None:
        return cached
    from django.utils import timezone

    from services.daily_feed import last_calculated_at

    stamp = last_calculated_at(timezone.localdate()) or ""
    cache.set("build-stamp", stamp, timeout=60)
    return stamp


def asset_versions(request=None) -> dict:
    """Context processor: ``{{ v_app }}`` / ``{{ v_web }}`` / ``{{ v_js }}`` for the
    stylesheet and script links, plus ``{{ build_stamp }}`` for the publish check's data
    freshness meta tag.

    ``v_js`` was added after the script kept the hand-typed ``?v=20260821-2`` it shipped
    with: the roll-over logic landed in ``static-site.js`` and the string was not bumped,
    so every returning visitor would have kept the cached copy and the nav would have
    labelled the wrong day. Exactly the failure this module was written to end, in the
    one file it had not been applied to.
    """
    return {
        "v_app": stylesheet_version("app.css"),
        "v_web": stylesheet_version("web.css"),
        "v_js": stylesheet_version("static-site.js"),
        "build_stamp": build_stamp(),
    }
