"""Daily opportunity snapshots.

Persists not just the score but the context needed to reproduce/interpret a
ranking later (owner decision 1, section 3.2): data cutoff, schedule provenance,
and which context (lineups / matchup / injuries) was available at capture time.
No snapshot-review UI is built in this pass — this is the storage seam plus the
write path.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from domain.models import DataStatus, Opportunity
from src.config import DB_PATH

_TABLE = "opportunity_snapshots"


def _resolve_key(league: str, market: str) -> str | None:
    from domain.markets import resolve
    return resolve(league, market)[0]


def _resolve_dir(league: str, market: str) -> str:
    from domain.markets import resolve
    return resolve(league, market)[1]


def _side_of(team: str | None, g) -> str | None:
    """Which side of a game a team is on, matched by any of its name forms."""
    if not team:
        return None
    t = team.strip().lower()
    away = {x.strip().lower() for x in (g.away_name, g.away_short, g.away_display) if x}
    home = {x.strip().lower() for x in (g.home_name, g.home_short, g.home_display) if x}
    return "away" if t in away else "home" if t in home else None


def _game_context(opp: Opportunity, games: dict) -> tuple[str | None, str | None, str | None]:
    """(opponent, opposing_sp, start_time) for a prop from its game record. Opposing
    SP is MLB-only; start_time is stored for later use (no sort UI yet)."""
    g = games.get(opp.game_id) if (games and opp.game_id) else None
    if g is None:
        return None, None, None
    side = _side_of(opp.team_name, g)
    if side == "away":
        opponent, sp = g.home_display, g.meta.get("home_pitcher")
    elif side == "home":
        opponent, sp = g.away_display, g.meta.get("away_pitcher")
    else:
        opponent, sp = None, None
    if opp.league != "MLB" or (sp and str(sp).upper() == "TBD"):
        sp = None
    start = g.start_time.isoformat() if g.start_time else None
    return opponent, sp, start

# Engine versions per league (fallback for props without a mapped market).
ENGINE_VERSIONS = {
    "MLB": "mlb-1hit-v0.1",
    "WNBA": "wnba-pra-v0.1",
}

# Per-market model version — BUMP the string whenever that scorer changes, so the
# Performance version-comparison can measure whether a change actually helped.
# (Cannot be reconstructed retroactively; history keeps whatever it was stamped with.)
MODEL_VERSIONS = {
    # v5: shrink recent form hard (0.70 -> 0.25) because plate appearances predict a
    # 1+ hit more than twice as well as recent hitting (+0.130 vs +0.054), with the score
    # scale re-tuned to hold the served share.
    "batter_hit": "batter-hit-v5",
    "batter_tb": "batter-tb-v2",   # ledger-refit: reachable-bar selection (clear ≥ .50)
    "batter_k": "batter-k-v1",     # two-directional, reachable-bar
    "batter_bb": "batter-bb-v1",   # over-only, reachable-bar
    # v3: threshold impressiveness from measured league rarity rather than the bar's
    # position in the list. The sp-v2 over-penalties are unchanged underneath.
    "sp_k": "sp-v3",
    "sp_hits": "sp-v3",
    # v3: 10-game clear rate weighted above the 5-game, trend term dropped (it correlated
    # +0.031 with clearing). Threshold selection unchanged from v2's reliability floor.
    "wnba_points": "wnba-pra-v3",
    "wnba_rebounds": "wnba-pra-v3",
    "wnba_assists": "wnba-pra-v3",
    # v1: reachable-bar, over-only, scored mostly on the clear rate. Registered
    # 2026-08-18 after measuring +32 to +51 points of lift over base rate across
    # 78,744 ingested player-games.
    "nfl_pass_yds": "nfl-props-v1",
    "nfl_rush_yds": "nfl-props-v1",
    "nfl_rec_yds": "nfl-props-v1",
    "nfl_receptions": "nfl-props-v1",
    "nfl_rush_att": "nfl-props-v1",
}


def _model_version(market_key: str | None, league: str) -> str | None:
    return MODEL_VERSIONS.get(market_key) or ENGINE_VERSIONS.get(league)


# Additive columns (added after CREATE so both fresh and existing DBs gain them).
_ADDED_COLUMNS = {
    "result": "TEXT",          # 'hit' | 'miss' | 'void' | NULL (pending)
    "actual_value": "REAL",    # the stat the player actually recorded that day
    "graded_at": "TEXT",       # ISO timestamp when graded
    "market_key": "TEXT",      # registry market-family key (resolved for legacy rows)
    "direction": "TEXT",       # 'over' | 'under' — graded comparison direction
    "opponent": "TEXT",        # the other team in the game (display name)
    "opposing_sp": "TEXT",     # MLB: the starting pitcher the player faces (else NULL)
    "start_time": "TEXT",      # scheduled first-pitch/tip ISO (stored; no sort UI yet)
    "void_reason": "TEXT",     # why a void was recorded (e.g. "did not play")
    "featured": "INTEGER",     # among the eight highest qualifying predictions
    "featured_rank": "INTEGER",# 1..8 on the Today page; NULL otherwise
}


def _ensure_added_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({_TABLE})")}
    added = False
    for col, col_type in _ADDED_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE {_TABLE} ADD COLUMN {col} {col_type}")
            added = True
    if added or col_null_exists(conn):
        _backfill_market_keys(conn)


def col_null_exists(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        f"SELECT 1 FROM {_TABLE} WHERE market_key IS NULL LIMIT 1").fetchone() is not None


def _backfill_market_keys(conn: sqlite3.Connection) -> None:
    """Resolve legacy rows (market text only) to a market_key + direction, once."""
    from domain.markets import resolve
    rows = conn.execute(
        f"SELECT rowid, league, market FROM {_TABLE} WHERE market_key IS NULL").fetchall()
    for rowid, league, market in rows:
        key, direction = resolve(league, market)
        conn.execute(f"UPDATE {_TABLE} SET market_key=?, direction=? WHERE rowid=?",
                     (key, direction, rowid))


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            snapshot_date TEXT NOT NULL,
            captured_on TEXT NOT NULL,
            calculated_at TEXT NOT NULL,
            league TEXT NOT NULL,
            game_id TEXT,
            player_id TEXT NOT NULL,
            player_name TEXT,
            team_id TEXT,
            team_name TEXT,
            market TEXT NOT NULL,
            threshold REAL,
            mode TEXT,
            opportunity_score INTEGER,
            stability_score INTEGER,
            component_values TEXT,
            support_evidence TEXT,
            risk_evidence TEXT,
            schedule_source_status TEXT,
            historical_data_cutoff TEXT,
            lineups_available INTEGER,
            matchup_context_available INTEGER,
            injury_context_available INTEGER,
            scoring_engine_version TEXT,
            PRIMARY KEY (snapshot_date, captured_on, league, player_id, market)
        )
        """
    )
    _ensure_added_columns(conn)


def _already_captured(conn: sqlite3.Connection, slate_token: str, captured_on: str) -> bool:
    row = conn.execute(
        f"SELECT 1 FROM {_TABLE} WHERE snapshot_date=? AND captured_on=? LIMIT 1",
        (slate_token, captured_on),
    ).fetchone()
    return row is not None


def write_daily_snapshot(
    *,
    slate_date: date,
    as_of: date,
    opportunities: list[Opportunity],
    schedule_status: dict[str, DataStatus] | None = None,
    games: dict | None = None,
    db_path: Path = DB_PATH,
    # Context availability — all False in this pass (honestly not yet included).
    lineups_available: bool = False,
    matchup_context_available: bool = False,
    injury_context_available: bool = False,
) -> int:
    """Write one snapshot per opportunity for ``slate_date``.

    ``games`` (game_id → SlateGame) supplies opponent / opposing-SP / start-time
    context. Idempotent per day: if a snapshot already exists for this slate date
    and today's capture date, nothing is written. Returns rows written.
    """
    if not opportunities:
        return 0
    now = datetime.now()
    slate_token = slate_date.isoformat()
    captured_on = now.date().isoformat()
    schedule_status = schedule_status or {}
    games = games or {}

    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        if _already_captured(conn, slate_token, captured_on):
            return 0
        written = 0
        from services.grading import CURATION_FLOOR, FEATURED_MAX
        qualifying = sorted(
            (opp for opp in opportunities
             if (opp.opportunity_score or 0) >= CURATION_FLOOR),
            key=lambda opp: (-(opp.opportunity_score or 0), opp.league,
                             opp.player_name or "", opp.market or ""),
        )
        featured_rank = {
            id(opp): rank for rank, opp in enumerate(qualifying[:FEATURED_MAX], 1)
        }
        for opp in opportunities:
            status = schedule_status.get(opp.league)
            opponent, opposing_sp, start_time = _game_context(opp, games)
            mkey = opp.market_key or _resolve_key(opp.league, opp.market)
            conn.execute(
                f"""
                INSERT OR IGNORE INTO {_TABLE} (
                    snapshot_date, captured_on, calculated_at, league, game_id,
                    player_id, player_name, team_id, team_name, market, threshold,
                    market_key, direction, opponent, opposing_sp, start_time,
                    mode, opportunity_score, stability_score, component_values,
                    support_evidence, risk_evidence, schedule_source_status,
                    historical_data_cutoff, lineups_available,
                    matchup_context_available, injury_context_available,
                    scoring_engine_version, featured, featured_rank
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    slate_token,
                    captured_on,
                    now.isoformat(timespec="seconds"),
                    opp.league,
                    opp.game_id,
                    opp.player_id,
                    opp.player_name,
                    opp.team_id,
                    opp.team_name,
                    opp.market,
                    float(opp.threshold) if opp.threshold is not None else None,
                    mkey,
                    opp.direction or _resolve_dir(opp.league, opp.market),
                    opponent,
                    opposing_sp,
                    start_time,
                    opp.mode.value,
                    opp.opportunity_score,
                    opp.stability_score,
                    json.dumps(opp.components),
                    json.dumps(opp.supporting_evidence),
                    json.dumps(opp.negative_evidence),
                    status.status.value if status else None,
                    as_of.isoformat(),
                    int(lineups_available),
                    int(matchup_context_available),
                    int(injury_context_available),
                    _model_version(mkey, opp.league),
                    int(id(opp) in featured_rank), featured_rank.get(id(opp)),
                ),
            )
            written += 1
        conn.commit()
    return written
