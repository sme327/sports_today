"""Cache-busting stylesheet URLs, derived from the files rather than remembered.

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


def asset_versions(request=None) -> dict:
    """Context processor: ``{{ v_app }}`` / ``{{ v_web }}`` for the stylesheet links."""
    return {
        "v_app": stylesheet_version("app.css"),
        "v_web": stylesheet_version("web.css"),
    }
