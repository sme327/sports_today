"""League adapters.

Each league is a plain module implementing the LeagueAdapter protocol and
registering an instance. Views and the router consume leagues only through the
registry, so adding a new league is one module plus one registration line.
"""

from leagues.base import LeagueAdapter, get_adapter, iter_adapters, register

# Import adapter modules for their registration side effects.
# Import order defines display order (MLB, WNBA, NBA, World Cup, MLS, NFL, NCAAF, NHL).
from leagues.mlb import adapter as _mlb  # noqa: F401
from leagues.wnba import adapter as _wnba  # noqa: F401
from leagues.nba import adapter as _nba  # noqa: F401
from leagues.world_cup import adapter as _world_cup  # noqa: F401
from leagues.mls import adapter as _mls  # noqa: F401
from leagues.nfl import adapter as _nfl  # noqa: F401
from leagues.ncaaf import adapter as _ncaaf  # noqa: F401
from leagues.nhl import adapter as _nhl  # noqa: F401

__all__ = ["LeagueAdapter", "get_adapter", "iter_adapters", "register"]
