"""League adapters.

Each league is a plain module implementing the LeagueAdapter protocol and
registering an instance. Views and the router consume leagues only through the
registry, so adding a new league is one module plus one registration line.
"""

from leagues.base import LeagueAdapter, get_adapter, iter_adapters, register

# Import adapter modules for their registration side effects.
from leagues.mlb import adapter as _mlb  # noqa: F401

__all__ = ["LeagueAdapter", "get_adapter", "iter_adapters", "register"]
