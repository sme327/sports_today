"""MLB team identity canonicalization.

Moved out of app.py. Maps any name/abbreviation the schedule feed or the
play-by-play workbook might use onto a stable canonical abbreviation, so schedule
teams and stored teams can be matched without relying on exact strings.
"""

from __future__ import annotations

import re

MLB_TEAM_ALIASES: dict[str, set[str]] = {
    "ARI": {"ARI", "Arizona Diamondbacks", "Diamondbacks"},
    "ATL": {"ATL", "Atlanta Braves", "Braves"},
    "BAL": {"BAL", "Baltimore Orioles", "Orioles"},
    "BOS": {"BOS", "Boston Red Sox", "Red Sox"},
    "CHC": {"CHC", "Chicago Cubs", "Cubs"},
    "CWS": {"CWS", "CHW", "Chicago White Sox", "White Sox"},
    "CIN": {"CIN", "Cincinnati Reds", "Reds"},
    "CLE": {"CLE", "Cleveland Guardians", "Guardians"},
    "COL": {"COL", "Colorado Rockies", "Rockies"},
    "DET": {"DET", "Detroit Tigers", "Tigers"},
    "HOU": {"HOU", "Houston Astros", "Astros"},
    "KC": {"KC", "KCR", "Kansas City Royals", "Royals"},
    "LAA": {"LAA", "Los Angeles Angels", "Angels"},
    "LAD": {"LAD", "Los Angeles Dodgers", "Dodgers"},
    "MIA": {"MIA", "Miami Marlins", "Marlins"},
    "MIL": {"MIL", "Milwaukee Brewers", "Brewers"},
    "MIN": {"MIN", "Minnesota Twins", "Twins"},
    "NYM": {"NYM", "New York Mets", "NY Mets", "Mets"},
    "NYY": {"NYY", "New York Yankees", "NY Yankees", "Yankees"},
    "ATH": {"ATH", "OAK", "Athletics", "Oakland Athletics"},
    "PHI": {"PHI", "Philadelphia Phillies", "Phillies"},
    "PIT": {"PIT", "Pittsburgh Pirates", "Pirates"},
    "SD": {"SD", "SDP", "San Diego Padres", "Padres"},
    "SEA": {"SEA", "Seattle Mariners", "Mariners"},
    "SF": {"SF", "SFG", "San Francisco Giants", "Giants"},
    "STL": {"STL", "St. Louis Cardinals", "Cardinals"},
    "TB": {"TB", "TBR", "Tampa Bay Rays", "Rays"},
    "TEX": {"TEX", "Texas Rangers", "Rangers"},
    "TOR": {"TOR", "Toronto Blue Jays", "Blue Jays"},
    "WSH": {"WSH", "WSN", "Washington Nationals", "Nationals"},
}

# Precomputed token -> canonical for O(1) lookup.
_TOKEN_TO_CANON: dict[str, str] = {}


def normalize_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


for _abbr, _aliases in MLB_TEAM_ALIASES.items():
    for _alias in _aliases:
        _TOKEN_TO_CANON[normalize_token(_alias)] = _abbr


def canonical_team(value: object) -> str | None:
    token = normalize_token(value)
    if not token:
        return None
    return _TOKEN_TO_CANON.get(token)
