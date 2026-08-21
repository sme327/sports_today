"""Small formatting helpers shared by rendering components."""

from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd

PACIFIC = ZoneInfo("America/Los_Angeles")


def format_game_time(raw: datetime | str | None) -> str:
    """Format a start time as e.g. '7:05 PM PT'. Accepts datetime or ISO string.

    This is the *publish-time* rendering, baked into the static export — i.e. the
    no-JS fallback. Wherever it is shown, also stamp ``utc_start_iso`` on the element
    (``data-start-utc``) so the site script can re-render it in the reader's own
    timezone: the owner reads the site from wherever they are, and a hardcoded PT is
    wrong the moment they travel."""
    if not raw:
        return "Time TBD"
    try:
        ts = pd.to_datetime(raw, utc=True).to_pydatetime().astimezone(PACIFIC)
        return ts.strftime("%-I:%M %p PT")
    except Exception:
        return str(raw)


def utc_start_iso(raw: datetime | str | None) -> str:
    """The UTC ISO stamp behind ``format_game_time``, or "" when unknown/unparseable.
    Uses the same normalisation (naive values are treated as UTC), so the fallback
    text and the client-side rendering can never describe different instants."""
    if not raw:
        return ""
    try:
        return pd.to_datetime(raw, utc=True).isoformat()
    except Exception:
        return ""


def logo_img(url: str | None, alt: str, css_class: str) -> str:
    """Render an <img> for a logo/headshot, or an empty placeholder div."""
    if not url:
        return f'<div class="{css_class}"></div>'
    return (
        f'<img class="{css_class}" src="{escape(str(url), quote=True)}" '
        f'alt="{escape(alt, quote=True)}">'
    )
