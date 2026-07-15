"""Today / Tomorrow date switch (custom joined capsule, same-tab links)."""

from __future__ import annotations


def date_switch_html(day: str) -> str:
    today_class = "active" if day == "today" else ""
    tomorrow_class = "active" if day == "tomorrow" else ""
    return (
        '<div class="date-toggle-wrap"><div class="date-toggle">'
        f'<a class="{today_class}" href="?day=today" target="_self">Today</a>'
        f'<a class="{tomorrow_class}" href="?day=tomorrow" target="_self">Tomorrow</a>'
        '</div></div>'
    )
