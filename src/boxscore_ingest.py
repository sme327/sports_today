"""Big Data Ball **box-score** ingest — NBA, WNBA, CBB and MLB game logs.

The vendor ships one row per player per game (or per team per game) for every sport, but
the app only ever had readers for two of them: MLB's plate-appearance play-by-play and
NFL's multi-row-header season feeds. This covers the rest, so seasons of NBA/CBB/WNBA/MLB
history can be **held** and queried before anything is built on top of them.

**This is storage, not analysis.** Nothing here scores, ranks or surfaces a thing. No
league adapter reads these tables. They exist so that when a feature wants multi-season
history, the data is already in SQLite rather than in a spreadsheet nobody can join to.

**Why a second reader rather than reusing ``nfl_ingest``.** The layouts genuinely differ,
and one of the differences is a trap: NFL's field map renames a ``1.0`` column to ``q1``,
which is right for a football quarter and wrong for a **baseball inning**. Sharing that
map would have silently mislabelled every MLB box score. ``_clean``/``_dedupe`` are shared
because they are pure text helpers; the field semantics are not.

Two header shapes appear, and the reader detects which:

* **Single row** — ``DATASET | GAME-ID | DATE | PLAYER-ID | …`` (most files).
* **Two-row banner** — a merged category row (``PLAYER INFORMATION``, ``BATTING``) above
  the field row, so ``AB`` becomes ``batting_ab``. Same idea as the NFL feeds.

Core column names drift between vintages of the *same* sport — ``TEAM`` vs ``OWN TEAM``,
``vs TEAM`` vs ``OPPONENT TEAM``, ``Player Name`` vs ``PLAYER FULL NAME``. Those are
normalised to one spelling so a query works across every file; **all other columns are
preserved as-is**, because which stat matters later is not knowable now.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config import DB_PATH
from src.nfl_ingest import _clean, _dedupe

# Category cells that label a *section* rather than a stat group — their columns keep the
# bare field name. ("BATTING" is a real group, so `AB` → `batting_ab`; "PLAYER
# INFORMATION" is not, so `TEAM` stays `team`.)
_BANNERS = {"game_information", "player_information", "game_info",
            "game_player_information", "team_information"}

# One spelling per concept. Keys are post-`_clean` variants seen across vintages.
_CORE_ALIASES = {
    "game_id": "game_id",
    "date": "game_date", "game_date": "game_date",
    "team": "team", "own_team": "team",
    "vs_team": "opponent", "opponent_team": "opponent", "opponent": "opponent",
    "opp_team": "opponent",
    "player_name": "player", "player_full_name": "player", "player": "player",
    "player_id": "player_id",
    "venue": "venue", "venue_r_h_n": "venue", "venue_r_h": "venue",
    "venue_road_home": "venue",
    "starter": "starter", "starter_y_n": "starter",
    "position": "position", "pos": "position",
    "dataset": "dataset", "bigdataball_dataset": "dataset",
    "start_time_et": "start_time_et",
    "association_division": "division",
    "arena_state": "arena",
    "game_date_2": "game_date",
    "player_name_2": "player",
}

# Columns that are always text, whatever they look like.
_TEXT_COLUMNS = {"dataset", "game_id", "game_date", "team", "opponent", "venue",
                 "starter", "player", "player_id", "position", "start_time_et",
                 "conference", "division", "arena", "status", "reason"}

# Fraction of a column's values that must parse as numbers before it is stored numeric.
# An allow-list alone was not enough: batter handedness ("L"/"R") is not on any obvious
# list of identity fields, and coercing it nulled **every** value — silently deleting the
# one column platoon splits need. Judging by content catches the fields nobody enumerated:
# umpire names, weather, pitcher names, odds written as text.
_NUMERIC_SHARE = 0.80

# The vendor renames the same field between vintages, and the two spellings land in two
# columns with no overlap — 2020-22 MLB hits in `bat_h`, 2023-24 in `batting_h`, so a
# query on either silently returns half the history. Everything canonicalises to one.
_VINTAGE_ALIASES = {
    "days_rest_team": "team_rest_days",
    "main_ref": "crew_chief", "crew": "referee_umpire",
    "spread_open": "opening_spread", "total_open": "opening_total",
    "spread_close": "closing_spread", "total_close": "closing_total",
    "closing_odd": "closing_odds",
    "1st_5_total_1st_5_moneyline": "first5_moneyline", "1st_5_runline": "first5_runline",
    "starting_pitcher": "pitch_starting_pitcher",
    "winning_losing_pitcher": "pitch_winning_losing_pitcher",
}


@dataclass(frozen=True)
class Sport:
    """How one sport's calendar maps onto a season label."""
    key: str
    label: str
    # What a bare-numbered column counts. Period headers arrive as a mix of ints and
    # floats (`6` beside `1.0`), so they clean to `6` and `1_0` — unusable and, worse,
    # inconsistent within one table. They are renamed `<period>_1 … <period>_9`.
    period: str
    # "calendar": the season is the year it is played in (MLB, WNBA — spring to autumn).
    # "spanning": the season crosses New Year, so games in Jan–Aug belong to the year
    # before (NBA, CBB — autumn to spring). Getting this backwards would file every
    # playoff game under the wrong season, which is why it is explicit per sport.
    season_style: str
    table_prefix: str


SPORTS: dict[str, Sport] = {
    "nba":  Sport("nba",  "NBA",       "period",  "spanning", "nba"),
    "cbb":  Sport("cbb",  "CBB",       "half",    "spanning", "cbb"),
    "wnba": Sport("wnba", "WNBA",      "period",  "calendar", "wnba_box"),
    "mlb":  Sport("mlb",  "MLB (box)", "inning",  "calendar", "mlb_box"),
}

_KINDS = ("player", "team", "dnp")

# Sheets that describe the workbook rather than carry game rows.
_META_SHEETS = {"metadata", "teams", "team_info", "team_metadata",
                "convert_date_format", "sample_fpts_calculation"}


def _is_banner_layout(raw: pd.DataFrame) -> bool:
    """Whether row 0 is a merged category row rather than the field names.

    A banner row is mostly empty — the merged cells read as NaN — while a real header row
    is dense. Checking emptiness rather than looking for known words means a new category
    label does not silently fall through to the wrong branch.
    """
    if len(raw) < 2:
        return False
    first = raw.iloc[0]
    filled = first.notna().sum()
    return filled <= max(2, len(first) // 4)


def _single_row_names(raw: pd.DataFrame) -> list[str]:
    return _dedupe([_clean(v) for v in raw.iloc[0].tolist()])


def _banner_names(raw: pd.DataFrame) -> list[str]:
    groups = [_clean(v) for v in raw.iloc[0].ffill().tolist()]
    fields = [_clean(v) for v in raw.iloc[1].tolist()]
    names = []
    for group, field in zip(groups, fields):
        prefix = "" if group in _BANNERS else group
        names.append(f"{prefix}_{field}" if prefix and field else field or prefix)
    return _dedupe(names)


_BARE_NUMBER = re.compile(r"^(\d+)(?:_0)?$")
# Prefixes a banner row adds in one vintage and not another, plus the "z" the vendor uses
# to sort odds columns last in a spreadsheet. Stripping them makes both vintages agree.
_STRIP_PREFIXES = ("odds_", "game_")
_LONG_TO_SHORT = (("batting_", "bat_"), ("pitching_", "pitch_"))


def _canonical(name: str) -> str:
    """One spelling for a field however this vintage of the feed happened to label it."""
    if name in ("game_id", "game_date"):
        return name
    for prefix in _STRIP_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix):
            name = name[len(prefix):]
    if name.startswith("z") and name[1:] in _VINTAGE_ALIASES or name.startswith("zline_"):
        name = name[1:]
    if name.startswith("z") and (name[1:].startswith(("opening", "closing", "halftime",
                                                      "box_score", "odds_"))):
        name = name[1:]
    for long, short in _LONG_TO_SHORT:
        if name.startswith(long):
            name = short + name[len(long):]
    return _VINTAGE_ALIASES.get(name, name)


def _apply_aliases(names: list[str], sport: Sport | None = None) -> list[str]:
    """Canonicalise core names, and give bare-numbered period columns a real name."""
    out = []
    for n in names:
        n = _CORE_ALIASES.get(n, n)
        m = _BARE_NUMBER.match(n)
        if m and sport is not None:
            n = f"{sport.period}_{int(m.group(1))}"
        else:
            n = _CORE_ALIASES.get(_canonical(n), _canonical(n))
        out.append(n)
    return _dedupe(out)


def pick_sheet(path: str | Path, kind: str) -> str:
    """The sheet holding ``kind`` rows.

    Sheet naming is inconsistent across vintages (``Player Data``, ``NBA-2025-26-PLAYER``,
    ``2022-MLB-PLAYER``), so this matches on substring after excluding the metadata
    sheets — several of which contain the word "team" and would otherwise win.
    """
    sheets = pd.ExcelFile(Path(path).expanduser()).sheet_names
    live = [s for s in sheets if _clean(s) not in _META_SHEETS]
    # "game_data" is how one MLB vintage names its team sheet — team rows, no "team"
    # anywhere in the label.
    want = {"player": ("player",), "team": ("team", "game_data"),
            "dnp": ("dnp", "did_not_play", "dnd", "nwt")}[kind]
    # DNP sheets also say "player", so they are excluded from a player match explicitly.
    dnp_marks = ("dnp", "did_not_play", "dnd", "nwt")
    for sheet in live:
        c = _clean(sheet)
        if kind == "player" and any(m in c for m in dnp_marks):
            continue
        if any(w in c for w in want):
            return sheet
    if kind == "player" and live:
        return live[0]
    raise KeyError(f"No '{kind}' sheet in {Path(path).name}; sheets: {sheets}")


def read_feed(path: str | Path, kind: str = "player", sheet: str | None = None,
              sport: Sport | None = None) -> pd.DataFrame:
    """One workbook sheet as a tidy frame with normalised core columns.

    Raises rather than guessing when the sheet has no usable date column — a feed we
    cannot place in time is one we cannot file under a season, and a silently seasonless
    table would be worse than no table.
    """
    if kind not in _KINDS:
        raise ValueError(f"kind must be one of {_KINDS}, got {kind!r}")
    path = Path(path).expanduser()
    sheet = sheet or pick_sheet(path, kind)
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    if raw.empty:
        raise ValueError(f"{path.name} [{sheet}] is empty")

    banner = _is_banner_layout(raw)
    names = _apply_aliases(_banner_names(raw) if banner else _single_row_names(raw), sport)
    df = raw.iloc[(2 if banner else 1):].copy()
    df.columns = names
    df = df.dropna(how="all").reset_index(drop=True)

    if "game_date" not in df.columns:
        raise KeyError(f"{path.name} [{sheet}] has no date column; got {list(df.columns)[:12]}")
    parsed = pd.to_datetime(df["game_date"], errors="coerce")
    if parsed.isna().all():
        raise ValueError(f"{path.name} [{sheet}] has no parseable dates")
    df["game_date"] = parsed.dt.date.astype("string")
    df = df.loc[parsed.notna()].reset_index(drop=True)
    df.attrs["parsed_dates"] = parsed.loc[parsed.notna()].reset_index(drop=True)

    # A feed with no game id cannot be joined to anything, and the project rule is to
    # never join on names. Storing it is fine; pretending it is usable is not.
    df.attrs["joinable"] = "game_id" in df.columns and df["game_id"].notna().any()
    for col in df.columns:
        if col in _TEXT_COLUMNS:
            df[col] = df[col].astype("string").str.strip()
            continue
        values = df[col]
        filled = values.notna().sum()
        numeric = pd.to_numeric(values, errors="coerce")
        if filled and numeric.notna().sum() / filled >= _NUMERIC_SHARE:
            df[col] = numeric
        else:
            df[col] = values.astype("string").str.strip()
    return df


def add_season(df: pd.DataFrame, sport: Sport) -> pd.DataFrame:
    """Label each row with its season, by the sport's own calendar."""
    parsed = df.attrs.get("parsed_dates")
    if parsed is None:
        parsed = pd.to_datetime(df["game_date"], errors="coerce")
    if sport.season_style == "calendar":
        season = parsed.dt.year
    else:
        # Autumn-to-spring: a January game belongs to the season that began last autumn.
        season = parsed.dt.year.where(parsed.dt.month >= 9, parsed.dt.year - 1)
    out = df.copy()
    out["season"] = season.astype("Int64").values
    return out


def _season_games(conn: sqlite3.Connection, table: str) -> dict[int, int]:
    """Games already stored per season, or ``{}`` if the table is new."""
    try:
        rows = conn.execute(
            f'SELECT season, COUNT(DISTINCT game_id) FROM "{table}" GROUP BY season')
        return {int(s): int(n) for s, n in rows if s is not None}
    except sqlite3.OperationalError:
        return {}


def _shrinking_seasons(conn: sqlite3.Connection, table: str,
                       df: pd.DataFrame) -> dict[int, tuple[int, int]]:
    """Seasons this write would make *smaller*, as ``{season: (have, incoming)}``.

    A later pull is not automatically a fuller one. The 2024-25 NBA feed was pulled on
    28 May and holds 1,312 games; the multi-season archive was pulled on 8 June and holds
    1,339 of the same season — the difference is the Finals. Replacing by recency alone
    silently deleted them, which is exactly the kind of loss nobody notices until the
    query returns a short answer months later.
    """
    if "game_id" not in df.columns or "season" not in df.columns:
        return {}
    have = _season_games(conn, table)
    incoming = (df.dropna(subset=["season"]).groupby(df["season"].astype("Int64"))
                ["game_id"].nunique().to_dict())
    return {int(s): (have[int(s)], int(n)) for s, n in incoming.items()
            if int(s) in have and int(n) < have[int(s)]}


def _replace_seasons(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    """Write additively **per season**: loading one year leaves the others alone.

    Mirrors ``nfl_ingest._replace_seasons``. A full-table replace would mean the folder's
    seven-season NBA archive and a current-season feed could never coexist.
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if exists:
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
        if "season" in cols and set(df.columns) == cols:
            for s in df["season"].dropna().unique():
                conn.execute(f'DELETE FROM "{table}" WHERE season = ?', (int(s),))
            df.to_sql(table, conn, if_exists="append", index=False)
            return
        # Column set drifted (a new vintage added stats) — rebuild rather than fail, but
        # only after keeping what the old table held for other seasons.
        old = pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
        if "season" in old.columns:
            old = old[~old["season"].isin(set(df["season"].dropna().unique()))]
        df = pd.concat([old, df], ignore_index=True)
    df.to_sql(table, conn, if_exists="replace", index=False)


def import_feed(path: str | Path, sport_key: str, kind: str = "player",
                db_path: str | Path = DB_PATH, sheet: str | None = None,
                force: bool = False) -> dict:
    """Read one workbook sheet into ``<prefix>_<kind>_games``. Returns a summary.

    A season already holding **more** games than this file offers is left alone and
    reported under ``skipped``; pass ``force=True`` to overwrite it anyway. Files arrive
    out of order and mid-season pulls are common, so recency is not a safe proxy for
    completeness.
    """
    if sport_key not in SPORTS:
        raise ValueError(f"Unknown sport {sport_key!r}; known: {sorted(SPORTS)}")
    sport = SPORTS[sport_key]
    df = add_season(read_feed(path, kind, sheet, sport), sport)
    suffix = "dnp" if kind == "dnp" else f"{kind}_games"
    table = f"{sport.table_prefix}_{suffix}"

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        skipped = {} if force else _shrinking_seasons(conn, table, df)
        if skipped:
            df = df[~df["season"].isin(skipped)]
        if not df.empty:
            _replace_seasons(conn, table, df)
    return {
        "table": table,
        "rows": len(df),
        "games": int(df["game_id"].nunique()) if "game_id" in df.columns and not df.empty else 0,
        "seasons": sorted(int(s) for s in df["season"].dropna().unique()) if not df.empty else [],
        "columns": len(df.columns),
        "date_range": (df["game_date"].min(), df["game_date"].max()) if not df.empty else (None, None),
        "skipped": skipped,
        "joinable": bool(df.attrs.get("joinable", False)),
    }
