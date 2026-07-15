"""Domain models shared across leagues and views.

These types are UI- and league-agnostic. Adapters translate league-specific
payloads into them so the Today page and opportunity feed can render one common
shape regardless of sport.
"""

from .models import (
    DataStatus,
    Evidence,
    Opportunity,
    OpportunityMode,
    SlateGame,
    SourceStatus,
)

__all__ = [
    "DataStatus",
    "Evidence",
    "Opportunity",
    "OpportunityMode",
    "SlateGame",
    "SourceStatus",
]
