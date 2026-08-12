import sqlite3
from datetime import date, datetime

from domain.models import DataStatus, Opportunity, OpportunityMode, SourceStatus
from services.migrations import ensure_schema
from services import snapshots


def _opp():
    return Opportunity(
        league="MLB", player_id="p1", player_name="Test", team_id=None,
        team_name="Mariners", market="1+ Hit", threshold=1,
        opportunity_score=88, stability_score=70,
        supporting_evidence=["a"], negative_evidence=["b"],
        components={"x": 1.0}, mode=OpportunityMode.SLATE, game_id="1",
    )


def test_write_captures_context_once_per_day(tmp_path):
    db = tmp_path / "s.db"
    ensure_schema(db)
    status = {"MLB": DataStatus("MLB StatsAPI", SourceStatus.LIVE, datetime.now())}
    n1 = snapshots.write_daily_snapshot(
        slate_date=date(2026, 7, 15), as_of=date(2026, 7, 15),
        opportunities=[_opp()], schedule_status=status, db_path=db,
    )
    n2 = snapshots.write_daily_snapshot(
        slate_date=date(2026, 7, 15), as_of=date(2026, 7, 15),
        opportunities=[_opp()], schedule_status=status, db_path=db,
    )
    assert n1 == 1
    assert n2 == 0  # idempotent per slate per day
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT schedule_source_status, historical_data_cutoff, "
            "lineups_available, scoring_engine_version FROM opportunity_snapshots"
        ).fetchone()
    assert row == ("live", "2026-07-15", 0, "batter-hit-v5")   # per-market model version


def test_no_opportunities_writes_nothing(tmp_path):
    db = tmp_path / "s.db"
    ensure_schema(db)
    assert snapshots.write_daily_snapshot(
        slate_date=date(2026, 7, 15), as_of=date(2026, 7, 15),
        opportunities=[], db_path=db,
    ) == 0


def test_game_context_opponent_and_opposing_sp():
    from datetime import timezone
    from domain.models import SlateGame
    from services.snapshots import _game_context

    g = SlateGame(league="MLB", game_id="G1",
                  start_time=datetime(2026, 8, 6, 23, 5, tzinfo=timezone.utc),
                  away_name="Los Angeles Dodgers", home_name="San Diego Padres",
                  away_short="Dodgers", home_short="Padres",
                  meta={"away_pitcher": "Tyler Glasnow", "home_pitcher": "Yu Darvish"})
    games = {"G1": g}

    def opp(league, team, market="1+ Hit", thr=1):
        return Opportunity(league=league, player_id="1", player_name="X", team_id=None,
                           team_name=team, market=market, threshold=thr,
                           opportunity_score=90, stability_score=50, game_id="G1")

    opponent, sp, start = _game_context(opp("MLB", "Los Angeles Dodgers"), games)
    assert opponent == "Padres" and sp == "Yu Darvish"          # faces the home starter
    assert start.startswith("2026-08-06")
    # home team faces the away starter
    assert _game_context(opp("MLB", "San Diego Padres"), games)[1] == "Tyler Glasnow"
    # WNBA prop → no opposing SP, opponent still resolves via name
    _, wnba_sp, _ = _game_context(opp("WNBA", "Los Angeles Dodgers", "15+ Points", 15), games)
    assert wnba_sp is None
    # unknown game → all None
    assert _game_context(opp("MLB", "Dodgers"), {}) == (None, None, None)


def test_engine_version_strings_match_the_scorers_actually_shipped():
    """A scorer change that does not update its version string makes the ledger lie about
    which engine produced a score — and version comparison is the only way we learn whether
    a change helped. It happened: `batter-hit-v5` and `sp-v3` shipped on 2026-08-10 while
    the ledger kept recording `batter-hit-v3` and `sp-v2`, and 449 rows had to be corrected
    after the fact. This pins the pair together."""
    from services.snapshots import MODEL_VERSIONS
    from src.opportunity import _HIT_SHRINK
    from src.pitcher_opportunity import _CLEAR_RATES
    from src.wnba_opportunity import _BASELINE_WEIGHT, _RECENT_WEIGHT

    # batter-hit-v5 is defined by shrinking recent form hard toward the league mean.
    assert (_HIT_SHRINK <= 0.35) == MODEL_VERSIONS["batter_hit"].endswith("v5")
    # sp-v3 is defined by taking impressiveness from measured rarity.
    assert bool(_CLEAR_RATES) == MODEL_VERSIONS["sp_k"].endswith("v3")
    assert MODEL_VERSIONS["sp_k"] == MODEL_VERSIONS["sp_hits"]
    # wnba-pra-v3 is defined by the 10-game window outweighing the 5-game.
    assert ((_BASELINE_WEIGHT > _RECENT_WEIGHT)
            == MODEL_VERSIONS["wnba_points"].endswith("v3"))
    for market in ("wnba_points", "wnba_rebounds", "wnba_assists"):
        assert MODEL_VERSIONS[market] == MODEL_VERSIONS["wnba_points"]
