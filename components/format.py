"""Small formatting helpers shared by rendering components."""

from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd

PACIFIC = ZoneInfo("America/Los_Angeles")


def format_game_time(raw: datetime | str | None) -> str:
    """Format a start time as e.g. '7:05 PM PT'. Accepts datetime or ISO string."""
    if not raw:
        return "Time TBD"
    try:
        ts = pd.to_datetime(raw, utc=True).to_pydatetime().astimezone(PACIFIC)
        return ts.strftime("%-I:%M %p PT")
    except Exception:
        return str(raw)


def logo_img(url: str | None, alt: str, css_class: str) -> str:
    """Render an <img> for a logo/headshot, or an empty placeholder div."""
    if not url:
        return f'<div class="{css_class}"></div>'
    return (
        f'<img class="{css_class}" src="{escape(str(url), quote=True)}" '
        f'alt="{escape(alt, quote=True)}">'
    )
