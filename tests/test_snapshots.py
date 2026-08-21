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
            "lineups_available, scoring_engine_version, featured, featured_rank "
            "FROM opportunity_snapshots"
        ).fetchone()
    assert row == ("live", "2026-07-15", 0, "batter-hit-v6", 1, 1)


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
    import inspect

    from services.snapshots import MODEL_VERSIONS
    from src import opportunity, pitcher_opportunity
    from src.opportunity import _HIT_SHRINK
    from src.pitcher_opportunity import _CLEAR_RATES
    from src.wnba_opportunity import _BASE_CLEAR, _BASELINE_BLEND, _RECENT_BLEND

    # batter-hit-v6 is defined by the v5 estimate (hard shrink) on the shared lift scale.
    assert _HIT_SHRINK <= 0.35
    on_lift_scale = "score_scale" in inspect.getsource(opportunity.score_hit_opportunities)
    assert on_lift_scale == MODEL_VERSIONS["batter_hit"].endswith("v6")
    # sp-v4 keeps v3's measured-rarity table and scores on the shared lift scale.
    assert bool(_CLEAR_RATES)
    assert ("score_scale" in inspect.getsource(pitcher_opportunity._score)) == \
        MODEL_VERSIONS["sp_k"].endswith("v4")
    assert MODEL_VERSIONS["sp_k"] == MODEL_VERSIONS["sp_hits"]
    # wnba-pra-v4 keeps v3's 10-over-5 weighting and adds the measured base-rate table.
    assert _BASELINE_BLEND > _RECENT_BLEND
    assert bool(_BASE_CLEAR) == MODEL_VERSIONS["wnba_points"].endswith("v4")
    for market in ("wnba_points", "wnba_rebounds", "wnba_assists"):
        assert MODEL_VERSIONS[market] == MODEL_VERSIONS["wnba_points"]
