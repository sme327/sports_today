"""Compact status chip (a pill, not a full-width alert bar)."""

from __future__ import annotations

from html import escape


def status_chip_html(text: str) -> str:
    return (
        '<div class="status-row">'
        '<div class="status-chip">'
        '<span class="status-dot"></span>'
        f'<span>{escape(text)}</span>'
        '</div>'
        '</div>'
    )
