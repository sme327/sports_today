"""Precomputed daily feed for fast public-page reads.

Network schedule retrieval and Pandas scoring belong in the morning/scheduled update,
not in an HTTP request. This service refreshes schedules, builds the complete normalized
opportunity population, writes the grading ledger, and stores a lossless display payload.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from time import perf_counter

import leagues  # noqa: F401 - populate adapter registry
from domain.models import DataStatus, Opportunity, OpportunityMode, SlateGame, SourceStatus
from leagues.base import LeagueAdapter, get_adapter, iter_adapters
from services import schedule_cache, snapshots
from services.calibration import annotate
from src.config import DB_PATH

_TABLE = "daily_opportunity_feed"
# Leagues whose adapter.opportunities() feeds the slate. Registering a market in
# domain/markets.py + MODEL_VERSIONS is not enough on its own — the league must also
# be listed here or its props are never scored, snapshotted, or graded. NFL was wired
# everywhere except this set for a day (2026-08-19), invisibly, because its staleness
# gate returns [] all preseason anyway. tests/test_daily_feed.py now guards the pair.
_ANALYSIS_LEAGUES = {"MLB", "WNBA", "NFL"}
_LEDGER_LIMIT = 100_000


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            slate_date TEXT PRIMARY KEY,
            calculated_at TEXT NOT NULL,
            opportunity_count INTEGER NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )


def _opportunity_dict(opp: Opportunity) -> dict:
    data = dataclasses.asdict(opp)
    data["mode"] = opp.mode.value
    status = opp.data_status
    data["data_status"] = (
        {
            "source": status.source,
            "status": status.status.value,
            "fetched_at": status.fetched_at.isoformat() if status.fetched_at else None,
            "detail": status.detail,
        }
        if status
        else None
    )
    return data


def _opportunity_from_dict(data: dict) -> Opportunity:
    data = dict(data)
    data["mode"] = OpportunityMode(data.get("mode", OpportunityMode.SLATE.value))
    raw_status = data.get("data_status")
    if raw_status:
        fetched_at = raw_status.get("fetched_at")
        data["data_status"] = DataStatus(
            source=raw_status.get("source") or "",
            status=SourceStatus(raw_status.get("status", SourceStatus.CACHED.value)),
            fetched_at=datetime.fromisoformat(fetched_at) if fetched_at else None,
            detail=raw_status.get("detail"),
        )
    return Opportunity(**data)


def store(slate_date: date, opportunities: list[Opportunity], *, db_path: Path = DB_PATH) -> None:
    payload = json.dumps([_opportunity_dict(opp) for opp in opportunities], separators=(",", ":"))
    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        conn.execute(
            f"""
            INSERT INTO {_TABLE} (slate_date, calculated_at, opportunity_count, payload)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(slate_date) DO UPDATE SET
                calculated_at=excluded.calculated_at,
                opportunity_count=excluded.opportunity_count,
                payload=excluded.payload
            """,
            (
                slate_date.isoformat(),
                datetime.now().isoformat(timespec="seconds"),
                len(opportunities),
                payload,
            ),
        )
        conn.commit()


def load(slate_date: date, *, db_path: Path = DB_PATH) -> tuple[list[Opportunity], datetime | None]:
    if not Path(db_path).exists():
        return [], None
    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        row = conn.execute(
            f"SELECT payload, calculated_at FROM {_TABLE} WHERE slate_date=?",
            (slate_date.isoformat(),),
        ).fetchone()
    if not row:
        return [], None
    try:
        opportunities = [_opportunity_from_dict(item) for item in json.loads(row[0])]
        calculated_at = datetime.fromisoformat(row[1])
    except (TypeError, ValueError, json.JSONDecodeError):
        return [], None
    return opportunities, calculated_at


def last_calculated_at(slate_date: date, *, db_path: Path = DB_PATH) -> str | None:
    """When this slate's feed was last precomputed, as the stored ISO string —
    without parsing the payload. Used as the published site's build stamp."""
    if not Path(db_path).exists():
        return None
    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        row = conn.execute(
            f"SELECT calculated_at FROM {_TABLE} WHERE slate_date=?",
            (slate_date.isoformat(),),
        ).fetchone()
    return str(row[0]) if row and row[0] else None


def _fetch(adapter: LeagueAdapter, slate_date: date):
    return adapter.fetch_schedule(slate_date)


def refresh_schedules(slate_date: date) -> dict[str, tuple[list[SlateGame], DataStatus]]:
    """Fetch every league concurrently, then persist results sequentially to SQLite."""
    adapters = iter_adapters()
    fetched: dict[str, tuple[list[SlateGame], DataStatus]] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(adapters)), thread_name_prefix="schedule") as pool:
        futures = {pool.submit(_fetch, adapter, slate_date): adapter for adapter in adapters}
        for future in as_completed(futures):
            adapter = futures[future]
            now = datetime.now()
            try:
                games = future.result()
                status = DataStatus(
                    adapter.source_name,
                    SourceStatus.LIVE if games else SourceStatus.EMPTY,
                    now,
                )
            except Exception as exc:
                cached = schedule_cache.read_latest_usable(
                    league=adapter.league, slate_date=slate_date
                )
                if cached:
                    games, cached_at = cached
                    status = DataStatus(
                        adapter.source_name,
                        SourceStatus.CACHED,
                        cached_at,
                        f"Live schedule unavailable; showing cached slate. ({exc})",
                    )
                else:
                    games = []
                    status = DataStatus(
                        adapter.source_name,
                        SourceStatus.ERROR,
                        None,
                        f"Live schedule unavailable and no cached slate exists. ({exc})",
                    )
            fetched[adapter.league] = (games, status)

    for adapter in adapters:
        games, status = fetched[adapter.league]
        if status.status in {SourceStatus.LIVE, SourceStatus.EMPTY}:
            schedule_cache.write(
                league=adapter.league,
                slate_date=slate_date,
                source=adapter.source_name,
                status=status.status,
                games=games,
                fetched_at=status.fetched_at,
            )
    return fetched


def load_cached_schedules(
    slate_date: date, *, db_path: Path = DB_PATH
) -> dict[str, tuple[list[SlateGame], DataStatus]]:
    out: dict[str, tuple[list[SlateGame], DataStatus]] = {}
    for adapter in iter_adapters():
        cached = schedule_cache.read_latest(
            league=adapter.league, slate_date=slate_date, db_path=db_path
        )
        if cached is None:
            out[adapter.league] = (
                [],
                DataStatus(
                    adapter.source_name,
                    SourceStatus.ERROR,
                    None,
                    "Awaiting the next scheduled data refresh.",
                ),
            )
        else:
            games, status, fetched_at, source = cached
            out[adapter.league] = (
                games,
                DataStatus(source or adapter.source_name, status, fetched_at),
            )
    return out


def _logo_map(games: list[SlateGame]) -> dict[str, str]:
    out: dict[str, str] = {}
    for game in games:
        for name, logo in (
            (game.away_name, game.away_logo),
            (game.away_short, game.away_logo),
            (game.away_abbr, game.away_logo),
            (game.home_name, game.home_logo),
            (game.home_short, game.home_logo),
            (game.home_abbr, game.home_logo),
        ):
            if name and logo:
                out[str(name)] = logo
    return out


def _stamp(opps: list[Opportunity], games: list[SlateGame], adapter: LeagueAdapter) -> list[Opportunity]:
    logos = _logo_map(games)
    game_ids: dict[str, str] = {}
    for game in games:
        for identity in (game.away_name, game.away_abbr, game.home_name, game.home_abbr):
            key = adapter.match_team(identity)
            if key:
                game_ids[key] = game.game_id
    return [
        dataclasses.replace(
            opp,
            image_url=opp.image_url or logos.get(str(opp.team_name)),
            game_id=opp.game_id
            or (game_ids.get(key) if (key := adapter.match_team(opp.team_name)) else None),
        )
        for opp in opps
    ]


def build_opportunities(
    slate_date: date, slates: dict[str, tuple[list[SlateGame], DataStatus]]
) -> list[Opportunity]:
    visible = {league: games for league, (games, _) in slates.items()}
    slate_opps: list[Opportunity] = []
    for league in _ANALYSIS_LEAGUES:
        games = visible.get(league) or []
        adapter = get_adapter(league)
        if not games or adapter is None:
            continue
        team_ids = sorted({team for game in games for team in game.team_identifiers})
        slate_opps.extend(
            _stamp(
                adapter.opportunities(
                    as_of=slate_date,
                    scheduled_team_ids=team_ids,
                    mode=OpportunityMode.SLATE,
                    limit=_LEDGER_LIMIT,
                ),
                games,
                adapter,
            )
        )

    mlb_games = visible.get("MLB") or []
    mlb = get_adapter("MLB")
    if mlb_games and mlb is not None:
        team_ids = sorted({team for game in mlb_games for team in game.team_identifiers})
        slate_opps.extend(
            _stamp(
                mlb.k_opportunities(
                    as_of=slate_date, scheduled_team_ids=team_ids, limit=_LEDGER_LIMIT
                ),
                mlb_games,
                mlb,
            )
        )
        probables = sorted(
            {
                (str(game.meta.get(key)), display)
                for game in mlb_games
                for key, display in (
                    ("away_pitcher", game.away_display),
                    ("home_pitcher", game.home_display),
                )
                if game.meta.get(key) and str(game.meta.get(key)).upper() != "TBD"
            }
        )
        if probables:
            from services.data_access import load_plate_appearances
            from services.mlb_pitcher_props import build_pitcher_opportunities

            pa = load_plate_appearances(as_of=slate_date)
            slate_opps.extend(
                _stamp(
                    build_pitcher_opportunities(pa, probables, slate_date), mlb_games, mlb
                )
            )
    annotate(slate_opps)
    slate_opps.sort(key=lambda opportunity: opportunity.sort_key, reverse=True)
    return slate_opps


def precompute_day(slate_date: date) -> dict:
    started = perf_counter()
    slates = refresh_schedules(slate_date)
    schedule_seconds = perf_counter() - started
    opportunities = build_opportunities(slate_date, slates)
    scoring_seconds = perf_counter() - started - schedule_seconds
    store(slate_date, opportunities)
    games = {
        str(game.game_id): game for league_games, _ in slates.values() for game in league_games
    }
    statuses = {league: status for league, (_, status) in slates.items()}
    ledger_rows = snapshots.write_daily_snapshot(
        slate_date=slate_date,
        as_of=slate_date,
        opportunities=opportunities,
        schedule_status=statuses,
        games=games,
    )
    matchup_started = perf_counter()
    matchup_pages = 0
    matchup_pages_by_league: dict[str, int] = {}
    matchup_errors = 0
    matchup_error_details: list[str] = []
    from services import matchup_cache
    from services.mlb_game_page import ENGINE_VERSION as MLB_ENGINE_VERSION, build_mlb_game_page
    from services.mls_game_page import ENGINE_VERSION as MLS_ENGINE_VERSION, build_mls_game_page
    from services.wnba_game_page import ENGINE_VERSION as WNBA_ENGINE_VERSION, build_wnba_game_page

    builders = (
        ("MLB", build_mlb_game_page, MLB_ENGINE_VERSION),
        ("WNBA", build_wnba_game_page, WNBA_ENGINE_VERSION),
        ("MLS", build_mls_game_page, MLS_ENGINE_VERSION),
    )
    for league, build_page, engine_version in builders:
        for game in slates.get(league, ([], None))[0]:
            try:
                page = build_page(game, slate_date, slate_date)
                matchup_cache.store(league, str(game.game_id), slate_date, engine_version, page)
                matchup_pages += 1
                matchup_pages_by_league[league] = matchup_pages_by_league.get(league, 0) + 1
            except Exception as exc:
                # A failed page must not fail the day, but a bare count is unactionable —
                # say which game and why, so the summary names the problem.
                matchup_errors += 1
                if len(matchup_error_details) < 20:
                    matchup_error_details.append(
                        f"{league} {game.game_id} ({game.away_display} @ {game.home_display}): "
                        f"{type(exc).__name__}: {exc}"
                    )
    return {
        "date": slate_date.isoformat(),
        "games": len(games),
        "opportunities": len(opportunities),
        "ledger_rows": ledger_rows,
        "matchup_pages": matchup_pages,
        "matchup_pages_by_league": matchup_pages_by_league,
        "matchup_errors": matchup_errors,
        "matchup_error_details": matchup_error_details,
        "matchup_seconds": round(perf_counter() - matchup_started, 3),
        "schedule_seconds": round(schedule_seconds, 3),
        "scoring_seconds": round(scoring_seconds, 3),
        "total_seconds": round(perf_counter() - started, 3),
    }


def precompute_days(days: list[date]) -> list[dict]:
    return [precompute_day(day) for day in days]
