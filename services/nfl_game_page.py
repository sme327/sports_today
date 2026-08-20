"""NFL matchup page model + builder (V1).

An evidence-first preview of one game, built from the ingested season feed: team
identity (offense/defense with league percentiles), head-to-head battlefields, recent
form, and — since these are completed games — the final result. Leakage-safe: the
preview uses only games **before** kickoff (``as_of`` = the game's date); the result is
shown separately as "what happened". Deterministic; every number traces to a game.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from services import nfl_analytics as A
from services import nfl_matchup
from services.nfl_matchup import MatchupCall
from services.nfl_repository import load_player_games, load_team_games
from src import nfl_opportunity
from src.config import DB_PATH

# v2 (2026-08-19): spotlights carry the opponent's measured effect on that player. The
# cache key is built from this string, so a page's *content* changing without a bump here
# means every cached page keeps serving the old HTML — which is exactly what happened
# while this was still v1.
ENGINE_VERSION = "nfl-matchup-v2"

# (label, season-table column, percentile column, higher-is-better)
_IDENTITY_ROWS = [
    ("Points / game", "points", "off_pct", True),
    ("Points allowed / game", "points_allowed", "def_pct", False),
    ("Yards / play", "yards_per_play", "efficiency_pct", True),
    ("Rush yards / game", "rush_yds", "rush_off_pct", True),
    ("Pass yards / game", "pass_yds", "pass_off_pct", True),
    ("3rd-down %", "third_down_pct", None, True),
    ("Turnover margin / game", "turnover_margin", "takeaway_pct", True),
]


@dataclass(frozen=True)
class NFLHero:
    away: str
    home: str
    game_date: str
    round_label: str
    away_record: str
    home_record: str
    away_score: int | None
    home_score: int | None
    winner: str | None          # "away" | "home" | None


@dataclass(frozen=True)
class NFLIdentityRow:
    label: str
    away_value: str
    home_value: str
    away_pct: int | None
    home_pct: int | None
    better: str                 # "away" | "home" | "even"


@dataclass(frozen=True)
class NFLFormLine:
    team: str
    results: str                # e.g. "W W L W L" (oldest→newest of the last 5)
    ppg: float
    papg: float
    games: int


@dataclass(frozen=True)
class NFLSpotlight:
    player: str
    position: str
    market: str                 # e.g. "75+ Rush Yards"
    support: str                # e.g. "96.8 avg · cleared 60% (6/10)"
    actual: float | None        # what the player did in this game
    result: str | None          # "hit" | "miss" | None (backtest of the leakage-safe pick)
    # The opponent's measured effect on this player, or None where no stat he plays is
    # matchup-sensitive. Receivers carry a "not-a-factor" call rather than nothing —
    # see services/nfl_matchup for why that is the honest answer and not an omission.
    matchup: "MatchupCall | None" = None


@dataclass(frozen=True)
class NFLGamePage:
    hero: NFLHero
    thesis: tuple[str, ...]     # a synthesized, evidence-based read (empty at season open)
    away_rest: int | None
    home_rest: int | None
    rest_note: str              # short-week / off-a-bye / rest-edge, or ""
    identity: tuple[NFLIdentityRow, ...]
    battlefields: tuple[A.Battlefield, ...]
    away_form: NFLFormLine | None
    home_form: NFLFormLine | None
    away_spotlights: tuple[NFLSpotlight, ...]
    home_spotlights: tuple[NFLSpotlight, ...]
    note: str                   # honest small-sample / season-opener language


def _fmt(value: float, pct: bool = False) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.0%}" if pct else f"{value:.1f}"


def _record(frame: pd.DataFrame, team: str) -> str:
    g = frame[frame["team"] == team]
    w = int(g["win"].sum())
    return f"{w}-{len(g) - w}"


def _form(frame: pd.DataFrame, team: str, n: int = 5) -> NFLFormLine | None:
    if frame.empty or "team" not in frame.columns:
        return None
    g = frame[frame["team"] == team].sort_values("game_date")
    if g.empty:
        return None
    last = g.tail(n)
    results = " ".join("W" if int(w) == 1 else "L" for w in last["win"])
    return NFLFormLine(team, results, round(last["points"].mean(), 1),
                       round(last["points_allowed"].mean(), 1), len(g))


def _short(name: str) -> str:
    return name.split()[-1] if name else name


def _poss(name: str) -> str:
    """Possessive — NFL nicknames are plural, so 'Bills' → 'Bills'', 'Team' → 'Team's'."""
    return name + ("'" if name.endswith("s") else "'s")


def _tier(pct) -> str:
    if pct is None or pd.isna(pct):
        return "unrated"
    pct = int(pct)
    return ("elite" if pct >= 85 else "strong" if pct >= 65 else
            "middling" if pct >= 35 else "weak")


def _thesis(a: str, h: str, ar, hr) -> tuple[str, ...]:
    """A calm, factual read of the matchup from the season profiles (no result)."""
    out = [
        f"{a}: {_tier(ar['off_pct'])} offense ({ar['points']:.0f} pts/g) vs "
        f"{_poss(h)} {_tier(hr['def_pct'])} defense ({hr['points_allowed']:.0f} allowed).",
        f"{h}: {_tier(hr['off_pct'])} offense ({hr['points']:.0f} pts/g) vs "
        f"{_poss(a)} {_tier(ar['def_pct'])} defense ({ar['points_allowed']:.0f} allowed).",
    ]
    watch = []
    for atk, dfn, off_c, def_c, phrase in (
        (a, h, "rush_off_pct", "rush_def_pct", "run game"),
        (h, a, "rush_off_pct", "rush_def_pct", "run game"),
        (a, h, "pass_off_pct", "pass_def_pct", "passing attack"),
        (h, a, "pass_off_pct", "pass_def_pct", "passing attack"),
    ):
        arow, drow = (ar, hr) if atk == a else (hr, ar)
        op, dp = arow.get(off_c), drow.get(def_c)
        if pd.notna(op) and pd.notna(dp) and int(op) - (100 - int(dp)) >= 30:
            watch.append(f"{_poss(atk)} {phrase} should test {dfn}")
    tm = ar["turnover_margin"] - hr["turnover_margin"]
    if abs(tm) >= 0.6:
        watch.append(f"{a if tm > 0 else h} own the turnover battle")
    if watch:
        out.append("Watch: " + "; ".join(watch[:2]) + ".")
    return tuple(out)


def _rest_note(a: str, h: str, ar: int | None, hr: int | None) -> str:
    parts = []
    for team, r in ((a, ar), (h, hr)):
        if r is not None and r <= 4:
            parts.append(f"{team} on a short week ({r} days)")
        elif r is not None and r >= 13:
            parts.append(f"{team} off a bye")
    if ar is not None and hr is not None and abs(ar - hr) >= 3 and not parts:
        more = a if ar > hr else h
        parts.append(f"{more} with a rest edge (+{abs(ar - hr)} days)")
    return "; ".join(parts)


def _spotlights(pg: pd.DataFrame, game_id: str, game_date: str, team: str,
                opponent: str = "", pg_all: pd.DataFrame | None = None) -> tuple[NFLSpotlight, ...]:
    """Key players' leakage-safe prop picks (from prior games) + how they actually did
    in this game — a per-player backtest of the pick — each with the opponent's measured
    effect on that player."""
    if pg.empty:
        return ()
    prior = pg[pg["game_date"].astype("string") < game_date]
    this = pg[pg["game_id"].astype("string") == str(game_id)]
    # One defence-rating table for the whole column: the ratings vary by date, not by
    # player, and rebuilding them per player made each page ~0.7s.
    tables = (nfl_matchup.ratings_for(pg_all if pg_all is not None else pg, game_date)
              if opponent else None)
    out: list[NFLSpotlight] = []
    for pid, name, pos in nfl_opportunity.key_players(prior[prior["team"] == team]):
        prop = nfl_opportunity.best_prop(prior[prior["player_id"] == pid], pos)
        if not prop:
            continue
        actual, result = None, None
        arow = this[this["player_id"] == pid]
        if not arow.empty:
            val = pd.to_numeric(arow.iloc[0].get(prop["stat"]), errors="coerce")
            if pd.notna(val):
                actual = float(val)
                result = "hit" if actual >= prop["threshold"] else "miss"
        cleared = int(round(prop["clear_rate"] * prop["games"]))
        support = f"{prop['avg']} avg · cleared {prop['clear_rate']:.0%} ({cleared}/{prop['games']})"
        # Props are scored on this season; the *defence* rating spans seasons, because a
        # defence has faced only a handful of qualifying quarterbacks by midseason and a
        # season-only rating would stay silent exactly when the page is most used.
        call = (nfl_matchup.outlook(pg_all if pg_all is not None else pg,
                                    pid, name, str(pos), opponent, game_date, tables)
                if opponent else None)
        out.append(NFLSpotlight(name, str(pos), f"{prop['threshold']}+ {prop['label']}",
                                support, actual, result, call))
    return tuple(out)


def build_nfl_game_page(game_id: str, db_path: Path = DB_PATH) -> NFLGamePage | None:
    tg = load_team_games(db_path=db_path)
    pg = load_player_games(db_path=db_path)
    return _build_nfl_game_page(game_id, tg, pg)


def build_nfl_game_pages(
    game_ids: list[str], db_path: Path = DB_PATH
) -> dict[str, NFLGamePage]:
    """Build many archive pages while loading the season tables only once."""
    tg = load_team_games(db_path=db_path)
    pg = load_player_games(db_path=db_path)
    pages = {}
    for game_id in game_ids:
        page = _build_nfl_game_page(str(game_id), tg, pg)
        if page is not None:
            pages[str(game_id)] = page
    return pages


def _build_nfl_game_page(
    game_id: str, tg: pd.DataFrame, pg: pd.DataFrame
) -> NFLGamePage | None:
    if tg.empty:
        return None
    rows = tg[tg["game_id"].astype("string") == str(game_id)]
    if len(rows) != 2:
        return None
    away_row = rows[rows["venue"] == "Road"]
    home_row = rows[rows["venue"] == "Home"]
    # Neutral-site or missing venue → fall back to the game_id "AWAY@HOME" order.
    if len(away_row) != 1 or len(home_row) != 1:
        away_row, home_row = rows.iloc[[0]], rows.iloc[[1]]
    away, home = str(away_row.iloc[0]["team"]), str(home_row.iloc[0]["team"])
    game_date = str(away_row.iloc[0]["game_date"])
    week = away_row.iloc[0]["week"]
    season_type = str(away_row.iloc[0]["season_type"])
    round_label = f"Wild Card / Playoffs · Wk {week}" if season_type == "postseason" else f"Week {week}"
    a_score = int(away_row.iloc[0]["final"]) if pd.notna(away_row.iloc[0]["final"]) else None
    h_score = int(home_row.iloc[0]["final"]) if pd.notna(home_row.iloc[0]["final"]) else None
    winner = None
    if a_score is not None and h_score is not None:
        winner = "away" if a_score > h_score else "home" if h_score > a_score else None

    # Scope everything to this game's season (records/form/rest are within-season).
    season = away_row.iloc[0].get("season")
    season_tg = tg[tg["season"] == season] if ("season" in tg.columns and pd.notna(season)) else tg
    # Leakage-safe preview: only games strictly before this one, this season.
    prior = season_tg[season_tg["game_date"].astype("string") < game_date]
    frame = A.team_game_frame(prior)
    table = A.team_season_table(frame)

    a_rec = _record(frame, away) if not frame.empty else "0-0"
    h_rec = _record(frame, home) if not frame.empty else "0-0"
    hero = NFLHero(away, home, game_date, round_label, a_rec, h_rec, a_score, h_score, winner)

    identity: list[NFLIdentityRow] = []
    battlefields: tuple[A.Battlefield, ...] = ()
    thesis: tuple[str, ...] = ()
    if not table.empty and away in table.index and home in table.index:
        a, h = table.loc[away], table.loc[home]
        thesis = _thesis(_short(away), _short(home), a, h)
        for label, col, pct_col, higher in _IDENTITY_ROWS:
            av, hv = a.get(col), h.get(col)
            apct = int(a[pct_col]) if pct_col and pd.notna(a.get(pct_col)) else None
            hpct = int(h[pct_col]) if pct_col and pd.notna(h.get(pct_col)) else None
            if apct is not None and hpct is not None:
                better = "away" if apct > hpct else "home" if hpct > apct else "even"
            elif pd.notna(av) and pd.notna(hv):
                better = ("away" if (av > hv) == higher else "home") if av != hv else "even"
            else:
                better = "even"
            is_pct = label.endswith("%")
            identity.append(NFLIdentityRow(label, _fmt(av, is_pct), _fmt(hv, is_pct),
                                           apct, hpct, better))
        battlefields = A.battlefields(table, away, home, _short(away), _short(home))

    games_in = int(len(frame[frame["team"] == away])) if not frame.empty else 0
    note = ("Season opener — no prior-form data yet." if games_in == 0 else
            "Early-season sample — form is thin." if games_in < 4 else "")

    pg_all = pg
    if not pg.empty and "season" in pg.columns and pd.notna(season):
        pg = pg[pg["season"] == season]
    # Each side's players are rated against the *other* side's defence.
    away_spot = _spotlights(pg, game_id, game_date, away, home, pg_all)
    home_spot = _spotlights(pg, game_id, game_date, home, away, pg_all)

    a_rest = A.rest_days(season_tg, away, game_date)
    h_rest = A.rest_days(season_tg, home, game_date)
    rest_note = _rest_note(_short(away), _short(home), a_rest, h_rest)

    return NFLGamePage(hero, thesis, a_rest, h_rest, rest_note,
                       tuple(identity), battlefields,
                       _form(frame, away), _form(frame, home),
                       away_spot, home_spot, note)


def list_seasons(db_path: Path = DB_PATH) -> list[int]:
    """Loaded seasons, newest first."""
    tg = load_team_games(db_path=db_path)
    if tg.empty or "season" not in tg.columns:
        return []
    return sorted((int(s) for s in tg["season"].dropna().unique()), reverse=True)


def list_weeks(season: int | None = None, db_path: Path = DB_PATH) -> list[dict]:
    """Available weeks with game counts for a season, for the archive browser."""
    tg = load_team_games(db_path=db_path)
    if tg.empty:
        return []
    if season is not None and "season" in tg.columns:
        tg = tg[tg["season"] == season]
    by_week = (tg.drop_duplicates("game_id").groupby(["week", "season_type"])
               .size().reset_index(name="games").sort_values("week"))
    return by_week.to_dict("records")


def list_games(week: int, season: int | None = None, db_path: Path = DB_PATH) -> list[dict]:
    """Games in a week (away/home, date, final, winner) for the archive browser."""
    tg = load_team_games(db_path=db_path)
    if tg.empty:
        return []
    if season is not None and "season" in tg.columns:
        tg = tg[tg["season"] == season]
    wk = tg[tg["week"] == week]
    out = []
    for gid, g in wk.groupby("game_id"):
        away = g[g["venue"] == "Road"]
        home = g[g["venue"] == "Home"]
        if len(away) != 1 or len(home) != 1:
            away, home = g.iloc[[0]], g.iloc[[1]]
        ar, hr = away.iloc[0], home.iloc[0]
        a_s = int(ar["final"]) if pd.notna(ar["final"]) else None
        h_s = int(hr["final"]) if pd.notna(hr["final"]) else None
        out.append({"game_id": str(gid), "game_date": str(ar["game_date"]),
                    "away": str(ar["team"]), "home": str(hr["team"]),
                    "away_score": a_s, "home_score": h_s})
    return sorted(out, key=lambda x: (x["game_date"], x["away"]))
