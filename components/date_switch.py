"""Today / Tomorrow date switch (custom joined capsule, same-tab links)."""

from __future__ import annotations


def date_switch_html(day: str, games_collapsed: bool = False) -> str:
    today_class = "active" if day == "today" else ""
    tomorrow_class = "active" if day == "tomorrow" else ""
    # Carry the collapsed state across Today/Tomorrow so it stays sticky.
    tail = "&games=off" if games_collapsed else ""
    return (
        '<div class="date-toggle-wrap"><div class="date-toggle">'
        f'<a class="{today_class}" href="?day=today{tail}" target="_self">Today</a>'
        f'<a class="{tomorrow_class}" href="?day=tomorrow{tail}" target="_self">Tomorrow</a>'
        '</div></div>'
    )
