"""Sports Today icon library (shared).

Monochrome outline SVGs, 24x24 viewBox, currentColor, 1.8px stroke, rounded caps
and joins. Sourced from icons/sports_today_icons_v1/*.svg, plus directional
recent-form arrows and positive/risk evidence marks in the same style. No emoji.
"""

from __future__ import annotations

_P = ('<svg class="mlb-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">')

_ICONS = {
    "power": _P + '<circle cx="10" cy="12" r="5.5"/><path d="M6.2 8.2c1.8 1.2 3.8 1.7 6 1.6M6.2 15.8c1.8-1.2 3.8-1.7 6-1.6"/><path d="M16.5 5.2l1.1-2M19.2 7.8l2-.8M18.9 11h2.2M18.1 14.1l1.6 1.5"/></svg>',
    "contact": _P + '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1.7"/><path d="M12 4v2M12 18v2M4 12h2M18 12h2"/></svg>',
    "discipline": _P + '<rect x="7" y="5" width="10" height="14" rx="1.8"/><path d="M12 5v14M7 12h10"/><circle cx="4.5" cy="8" r="1"/><circle cx="19.5" cy="15.5" r="1"/></svg>',
    "speed": _P + '<circle cx="15" cy="12" r="4.5"/><path d="M12 8.7c1.3.9 2.8 1.3 4.5 1.2M12 15.3c1.3-.9 2.8-1.3 4.5-1.2"/><path d="M3 7.5h5M2 12h6M4 16.5h4"/></svg>',
    "risp": _P + '<path d="M12 3l8 8-8 8-8-8 8-8z"/><path d="M12 7l4 4-4 4-4-4 4-4z"/><circle cx="8" cy="11" r="1.2" fill="currentColor" stroke="none"/><circle cx="16" cy="11" r="1.2" fill="currentColor" stroke="none"/></svg>',
    "matchup": _P + '<path d="M6 4l12 16"/><path d="M18 4L6 20"/><path d="M4.5 5.5L7 3M17 3l2.5 2.5M4.5 18.5L7 21M17 21l2.5-2.5"/></svg>',
    "storyline": _P + '<path d="M5 5.5h14v13H5z"/><path d="M8 9h8M8 12h8M8 15h5"/><path d="M5 5.5l2-2h10l2 2"/></svg>',
    "opportunity": _P + '<circle cx="12" cy="12" r="8"/><path d="M12 4v4M12 16v4M4 12h4M16 12h4"/><circle cx="12" cy="12" r="2"/></svg>',
    "confidence": _P + '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 8 8h-8z" fill="currentColor" stroke="none" opacity=".28"/><path d="M12 12l4-4"/><circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/></svg>',
    "game_shape": _P + '<path d="M8 3h8l5 9-5 9H8l-5-9 5-9z"/><path d="M8 12h8"/><circle cx="12" cy="12" r="2"/></svg>',
    "strikeout": _P + '<circle cx="14.5" cy="12" r="4.5"/><path d="M11.5 8.7c1.3.9 2.8 1.3 4.5 1.2M11.5 15.3c1.3-.9 2.8-1.3 4.5-1.2"/><path d="M3 8h5M2 12h6M4 16h4"/></svg>',
    "recent_form": _P + '<path d="M4 17l5-5 3 3 6-7"/><path d="M15 8h3v3"/><path d="M4 20h16"/></svg>',
    "form-up": _P + '<path d="M4 16l6-6 4 4 6-7"/><path d="M17 7h3v3"/></svg>',
    "form-down": _P + '<path d="M4 8l6 6 4-4 6 7"/><path d="M17 17h3v-3"/></svg>',
    "form-steady": _P + '<path d="M4 12h16"/></svg>',
    # Evidence marks (same style): a positive check-in-circle and a risk triangle.
    "positive": _P + '<circle cx="12" cy="12" r="9"/><path d="M8 12.4l2.6 2.6L16 9"/></svg>',
    "risk": _P + '<path d="M12 3.5l8.5 15h-17z"/><path d="M12 10v4.2M12 17.2h.01"/></svg>',
}
_ICONS["advantage"] = _ICONS["confidence"]
_ICONS["swing"] = _ICONS["strikeout"]
_ICONS["momentum"] = _ICONS["recent_form"]
_ICONS["baseball"] = _ICONS["storyline"]


def icon(name: str) -> str:
    return _ICONS.get(name, "")
