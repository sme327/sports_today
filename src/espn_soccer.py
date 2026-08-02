"""Neutral ESPN soccer scoreboard client (competition-parameterized).

One parser for any ESPN soccer competition (MLS = ``usa.1``, and the same shape
serves other leagues). Returns normalized dicts the league adapters convert into
``SlateGame``. Everything here is real provider data: teams, club logos, W-D-L
records, recent form (last five results), brand colors, venue, kickoff, and
Final-score V1 fields. No statistics are invented.

Kept separate from ``src/world_cup_api`` on purpose: World Cup uses national
flags and a hardcoded bracket fallback; club competitions use club logos and have
no fallback. A future refactor may migrate World Cup onto this client.
"""

from __future__ import annotations

from datetime import date

import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"

# Known competition slugs (extend as leagues are added).
MLS = "usa.1"


def _score(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _state(status: dict) -> str:
    return {"pre": "pre", "in": "live", "post": "final"}.get(
        status.get("type", {}).get("state"), "pre")


def _winner(competitors: list[dict]) -> str | None:
    for c in competitors:
        if c.get("winner"):
            return c.get("homeAway")
    return None


def _record(competitor: dict) -> str | None:
    """The team's overall W-D-L summary, e.g. '5-5-5'."""
    for rec in competitor.get("records") or []:
        if rec.get("type") == "total" or rec.get("name") == "All Splits":
            return rec.get("summary")
    recs = competitor.get("records") or []
    return recs[0].get("summary") if recs else None


def _form(competitor: dict) -> tuple[str, ...]:
    """Recent results oldest→newest as a tuple like ('D','W','L','W','D')."""
    raw = competitor.get("form") or ""
    return tuple(ch for ch in str(raw).upper() if ch in ("W", "D", "L"))


def _color(team: dict) -> str | None:
    c = team.get("color")
    if not c:
        return None
    c = str(c).lstrip("#")
    return f"#{c}" if len(c) in (3, 6) else None


def _broadcast(competition: dict) -> str:
    names: list[str] = []
    for item in competition.get("broadcasts") or []:
        names.extend(item.get("names") or [])
    return ", ".join(dict.fromkeys(names))


def _competition_label(event: dict, slug: str) -> str:
    season = event.get("season") or {}
    slug_name = season.get("slug") or ""
    pretty = {
        "regular-season": "MLS Regular Season",
        "post-season": "MLS Cup Playoffs",
    }
    if slug == MLS:
        return pretty.get(slug_name, "Major League Soccer")
    return slug_name.replace("-", " ").title() or slug


def parse(payload: dict, slug: str) -> list[dict]:
    """Parse an ESPN soccer scoreboard payload into normalized game dicts."""
    games: list[dict] = []
    for event in payload.get("events", []):
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})
        home_team = home.get("team", {})
        away_team = away.get("team", {})
        status = event.get("status", {})
        stype = status.get("type", {})
        season = event.get("season") or {}
        games.append({
            "game_id": event.get("id"),
            "game_date": event.get("date"),
            "status": stype.get("detail") or stype.get("description"),
            # Stable identifiers + season context (used by the MLS collector; the
            # SlateGame adapters ignore keys they don't read).
            "away_id": str(away_team.get("id")) if away_team.get("id") else None,
            "home_id": str(home_team.get("id")) if home_team.get("id") else None,
            "season_year": season.get("year"),
            "season_type": season.get("type"),
            "season_slug": season.get("slug"),
            "completed": bool(stype.get("completed")),
            "away": away_team.get("displayName"),
            "home": home_team.get("displayName"),
            "away_short": away_team.get("shortDisplayName") or away_team.get("name"),
            "home_short": home_team.get("shortDisplayName") or home_team.get("name"),
            "away_abbr": away_team.get("abbreviation"),
            "home_abbr": home_team.get("abbreviation"),
            "away_logo": away_team.get("logo"),
            "home_logo": home_team.get("logo"),
            "away_color": _color(away_team),
            "home_color": _color(home_team),
            "away_record": _record(away),
            "home_record": _record(home),
            "away_form": _form(away),
            "home_form": _form(home),
            "venue": (competition.get("venue") or {}).get("fullName"),
            "competition": _competition_label(event, slug),
            "broadcast": _broadcast(competition),
            # Final-score V1 fields.
            "away_score": _score(away.get("score")),
            "home_score": _score(home.get("score")),
            "state": _state(status),
            "winner": _winner(competitors),
            "status_detail": stype.get("shortDetail") or stype.get("detail"),
        })
    return games


def schedule(competition_slug: str, game_date: date | str) -> list[dict]:
    """Fetch and parse a competition's games for a date. [] on any failure."""
    date_key = game_date.isoformat() if hasattr(game_date, "isoformat") else str(game_date)
    token = date_key.replace("-", "")
    try:
        response = requests.get(
            BASE.format(slug=competition_slug),
            params={"dates": token, "limit": 30},
            timeout=15,
        )
        response.raise_for_status()
        return parse(response.json(), competition_slug)
    except Exception:
        return []


# ============================================================================
# Match summary + standings (added for MLS team-stat integration, Phase 3B).
# Pure parsers only. Retry/backoff, date-range orchestration, incremental logic,
# and SQLite writes live in src/mls_collector.py, NOT here.
# ============================================================================

SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary"
STANDINGS = "https://site.web.api.espn.com/apis/v2/sports/soccer/{slug}/standings"


def fetch_summary(competition_slug: str, event_id: str,
                  *, session: requests.Session | None = None, timeout: int = 25) -> dict:
    """Fetch one match's summary payload. Raises on HTTP/JSON error (the caller
    owns retry/backoff)."""
    getter = session.get if session is not None else requests.get
    resp = getter(SUMMARY.format(slug=competition_slug),
                  params={"event": str(event_id)}, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected non-object summary JSON for event {event_id}")
    return payload


def fetch_standings(competition_slug: str, season: int,
                    *, session: requests.Session | None = None, timeout: int = 25) -> dict:
    """Fetch the competition standings payload for a season. Raises on error."""
    getter = session.get if session is not None else requests.get
    resp = getter(STANDINGS.format(slug=competition_slug),
                  params={"season": int(season)}, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise ValueError("Unexpected non-object standings JSON")
    return payload


def _int(display: object) -> int | None:
    """Coerce an ESPN stat displayValue to int. Missing → None; '0' → 0 (valid
    zero); non-numeric → None. Never invents a zero."""
    if display is None:
        return None
    try:
        return int(round(float(str(display).replace(",", "").strip())))
    except (TypeError, ValueError):
        return None


def _float(display: object) -> float | None:
    if display is None:
        return None
    try:
        return float(str(display).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _pct(numer: int | None, denom: int | None) -> float | None:
    """A 0–100 accuracy percentage derived from raw counts. NULL when the
    denominator is missing or zero (never 0%)."""
    if numer is None or denom is None or denom == 0:
        return None
    return round(100.0 * numer / denom, 1)


# Provider stat name → our column name. All values come from ``displayValue``
# (the provider leaves numeric ``value`` null for soccer). Accuracy percentages
# are NOT taken from the provider (its *Pct fields are lossily rounded to one
# decimal); they are derived from the counts below.
_TEAM_STAT_MAP = {
    "possessionPct": "possession_pct",   # 0–100, provider-reported (no raw count)
    "totalShots": "total_shots",
    "shotsOnTarget": "shots_on_target",
    "blockedShots": "blocked_shots",
    "wonCorners": "won_corners",
    "foulsCommitted": "fouls_committed",
    "offsides": "offsides",
    "saves": "saves",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
    "totalPasses": "total_passes",
    "accuratePasses": "accurate_passes",
    "totalCrosses": "total_crosses",
    "accurateCrosses": "accurate_crosses",
    "totalTackles": "total_tackles",
    "interceptions": "interceptions",
    "totalClearance": "total_clearances",
    "penaltyKickGoals": "pk_goals",
    "penaltyKickShots": "pk_shots",
}
_COUNT_COLUMNS = {v for k, v in _TEAM_STAT_MAP.items() if k != "possessionPct"}


def parse_team_stats(summary_payload: dict) -> list[dict]:
    """Two per-team stat dicts from a summary payload, keyed by ``team_id``.

    Raises ValueError if the match structure is invalid (not exactly two team
    blocks with team IDs). Missing individual stats stay None; a present '0' is a
    valid zero. Accuracy percentages are derived from counts, not the provider's
    rounded fields.
    """
    teams = (summary_payload.get("boxscore") or {}).get("teams") or []
    if len(teams) != 2:
        raise ValueError(f"Expected 2 team stat blocks, found {len(teams)}")

    parsed: list[dict] = []
    ids: list[str] = []
    for block in teams:
        tid = str((block.get("team") or {}).get("id") or "")
        if not tid:
            raise ValueError("Team stat block missing team id")
        ids.append(tid)
        by_name = {s.get("name"): s.get("displayValue") for s in block.get("statistics") or []}
        row: dict = {"team_id": tid, "is_home": 1 if block.get("homeAway") == "home" else 0}
        for prov, col in _TEAM_STAT_MAP.items():
            if prov == "possessionPct":
                row[col] = _float(by_name.get(prov)) if prov in by_name else None
            else:
                row[col] = _int(by_name.get(prov)) if prov in by_name else None
        # Derived accuracy percentages (0–100) from raw counts.
        row["shot_pct"] = _pct(row.get("shots_on_target"), row.get("total_shots"))
        row["pass_pct"] = _pct(row.get("accurate_passes"), row.get("total_passes"))
        row["cross_pct"] = _pct(row.get("accurate_crosses"), row.get("total_crosses"))
        parsed.append(row)

    for row in parsed:
        row["opponent_id"] = ids[1] if row["team_id"] == ids[0] else ids[0]
    return parsed


def parse_match_meta(summary_payload: dict) -> dict:
    """Venue id/name, attendance, and referee from a summary payload's gameInfo.

    Match date/teams/scores/state come from the scoreboard event, not here.
    """
    gi = summary_payload.get("gameInfo") or {}
    venue = gi.get("venue") or {}
    officials = gi.get("officials") or []
    referee = None
    for off in officials:
        pos = (off.get("position") or {}).get("name") or (off.get("position") or {}).get("displayName")
        if pos in (None, "Referee", "Head Referee") and off.get("displayName"):
            referee = off.get("displayName")
            break
    if referee is None and officials:
        referee = officials[0].get("displayName")
    return {
        "venue_id": str(venue.get("id")) if venue.get("id") else None,
        "venue": venue.get("fullName"),
        "attendance": gi.get("attendance") if isinstance(gi.get("attendance"), int) else _int(gi.get("attendance")),
        "referee": referee,
    }


def parse_standings(standings_payload: dict) -> list[dict]:
    """One row per team from the competition standings payload.

    Reads the conference groups (``children``); each entry carries rank, points,
    W/D/L, goals for/against, and goal difference. Empty list if none present.
    """
    def _stat(entry: dict, name: str):
        for s in entry.get("stats") or []:
            if isinstance(s, dict) and s.get("name") == name:
                v = s.get("value")
                if v is None:
                    v = s.get("displayValue")
                try:
                    return int(round(float(v)))
                except (TypeError, ValueError):
                    return None
        return None

    rows: list[dict] = []
    for group in standings_payload.get("children") or []:
        conference = group.get("name")
        entries = ((group.get("standings") or {}).get("entries")) or []
        for e in entries:
            team = e.get("team") or {}
            tid = str(team.get("id") or e.get("id") or "")
            if not tid:
                continue
            rows.append({
                "team_id": tid,
                "conference": conference,
                "conference_rank": _stat(e, "rank"),
                "points": _stat(e, "points"),
                "games_played": _stat(e, "gamesPlayed"),
                "wins": _stat(e, "wins"),
                "draws": _stat(e, "ties"),
                "losses": _stat(e, "losses"),
                "goals_for": _stat(e, "pointsFor"),
                "goals_against": _stat(e, "pointsAgainst"),
                "goal_difference": _stat(e, "pointDifferential"),
            })
    return rows


# --------------------------------------------------- match events (Option C) --
def _event_category(type_text: str) -> str | None:
    """Coarse category, or None to skip (kickoff, halftime, VAR, …)."""
    low = (type_text or "").lower()
    if "yellow card" in low or "red card" in low:
        return "card"
    if "substitution" in low:
        return "sub"
    if "own goal" in low:
        return "own_goal"
    if "penalty" in low and "scored" not in low:      # missed/saved penalty
        return "penalty_miss"
    if "goal" in low or ("penalty" in low and "scored" in low):
        return "goal"
    return None


_SET_PIECE_PHRASES = (
    "following a corner", "from a corner", "corner kick", "following a set piece",
    "from a free kick", "direct free kick", "set piece", "set-piece",
)


def _goal_source(type_text: str, text: str) -> str:
    """Honest goal-source category from the structured type + the provider
    sentence. Precise phrase matching only — bare "corner" is avoided because the
    provider also uses it for shot placement ("bottom right corner").

    penalty → set_piece → header → open_play (priority order).
    """
    low_t, txt = (type_text or "").lower(), (text or "").lower()
    if "penalty" in low_t:
        return "penalty"
    if "free-kick" in low_t or any(ph in txt for ph in _SET_PIECE_PHRASES):
        return "set_piece"
    if "header" in low_t:
        return "header"
    return "open_play"


def _minute_bucket(clock_display: str, period) -> tuple[int | None, int, str | None]:
    """Parse a clock like "47'", "45'+7'", "90'+1'" → (base minute, stoppage,
    half-aware bucket). Stoppage time is bucketed to the end of its half."""
    s = (clock_display or "").replace("'", "").strip()
    if not s:
        return (None, 0, None)
    stoppage = 0
    if "+" in s:
        base_s, extra_s = s.split("+", 1)
        base, stoppage = _int(base_s), (_int(extra_s) or 0)
        bucket = "31-45" if period == 1 else "76-90+"
    else:
        base = _int(s)
        if base is None:
            return (None, 0, None)
        bucket = ("0-15" if base <= 15 else "16-30" if base <= 30 else "31-45"
                  if base <= 45 else "46-60" if base <= 60 else "61-75"
                  if base <= 75 else "76-90+")
    return (base, stoppage, bucket)


def parse_key_events(summary_payload: dict) -> list[dict]:
    """Normalized goal/card/substitution events from a summary payload.

    Each row carries the minute + half-aware bucket, the event's team id, a goal
    source proxy (open_play / set_piece / penalty), and the involved athletes
    (scorer + assist, or sub in + out, or carded player). Non-material events
    (kickoff, halftime, VAR reviews) are skipped. `match_id` is filled by the
    collector.
    """
    rows: list[dict] = []
    for e in summary_payload.get("keyEvents") or []:
        type_text = (e.get("type") or {}).get("text") or ""
        category = _event_category(type_text)
        if category is None:
            continue
        base, stoppage, bucket = _minute_bucket(
            (e.get("clock") or {}).get("displayValue"), (e.get("period") or {}).get("number"))
        participants = e.get("participants") or []

        def athlete(i: int) -> tuple[str | None, str | None]:
            if i < len(participants):
                a = participants[i].get("athlete") or {}
                return (str(a.get("id")) if a.get("id") else None, a.get("displayName"))
            return (None, None)

        p1, p2 = athlete(0), athlete(1)
        rows.append({
            "match_id": None,
            "seq": str(e.get("id")) if e.get("id") is not None else None,
            "type": type_text,
            "category": category,
            "goal_source": _goal_source(type_text, e.get("text") or "")
            if category == "goal" else None,
            "minute": base,
            "stoppage": stoppage,
            "period": (e.get("period") or {}).get("number"),
            "bucket": bucket,
            "team_id": str((e.get("team") or {}).get("id"))
            if (e.get("team") or {}).get("id") else None,
            "primary_id": p1[0], "primary_name": p1[1],      # scorer / carded / sub-in
            "secondary_id": p2[0], "secondary_name": p2[1],  # assist / sub-out
        })
    return rows
