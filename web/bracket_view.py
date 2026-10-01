"""The MLB postseason pages: the whole bracket, and one page per series.

The arithmetic lives in ``services/mlb_bracket``; this module only arranges it for the
two templates and decides which games have a matchup page to link to.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from components.format import format_game_time, utc_start_iso
from services import mlb_bracket
from services.mlb_bracket import Bracket, Game, Series, Side

# Left to right across the page: the AL climbs toward the middle, the NL mirrors it.
_COLUMNS = (
    ("F", "AL", "Wild Card"), ("D", "AL", "Division Series"),
    ("L", "AL", "ALCS"), ("W", None, "World Series"),
    ("L", "NL", "NLCS"), ("D", "NL", "Division Series"), ("F", "NL", "Wild Card"),
)


def matchup_slugs(league: str, today: date) -> dict[str, str]:
    """``{game_id: day slug}`` for every game on a precomputed slate day.

    Only those games have a matchup page, and the link must carry the *same* ``day``
    slug the slate card uses, because the exporter keys a matchup page on its full query
    string — a guessed slug resolves locally and 404s on the published site.
    """
    from services import daily_feed
    from web.today import DAY_OFFSETS

    slug_for: dict[str, str] = {}
    for slug, offset in DAY_OFFSETS.items():
        slate = daily_feed.load_cached_schedules(today + timedelta(days=offset))
        for game in (slate.get(league, ([], None))[0] or []):
            slug_for.setdefault(str(game.game_id), slug)
    return slug_for


def _day(game: Game) -> str:
    raw = game.official_date or (game.start or "")[:10]
    try:
        return datetime.fromisoformat(raw).strftime("%a, %b %-d")
    except ValueError:
        return raw


def _time(game: Game) -> str:
    return "Time TBD" if game.time_tbd else format_game_time(game.start)


def _side(series: Series, side: Side) -> dict:
    winner = series.winner
    return {
        "id": side.team_id, "seed": side.seed, "name": side.label,
        "compact": side.compact_label,
        "full_name": side.name if not side.placeholder else side.label,
        "logo": side.logo, "wins": side.wins, "placeholder": side.placeholder,
        "won": bool(winner and winner is side),
        "out": bool(winner and winner is not side),
        "feeder_href": (mlb_bracket.series_href(side.feeder)
                        if side.placeholder and side.feeder else ""),
    }


def _status(series: Series) -> str:
    """The one line under a series in the bracket."""
    if series.state == "decided":
        return series.summary
    nxt = series.next_game
    if series.state == "live":
        live = next(g for g in series.games if g.state == "live")
        base = f"Game {live.number} under way"
        return base if series.summary.startswith("Best of") else f"{base} · {series.summary}"
    if series.state == "underway":
        when = f" · Game {nxt.number} {_day(nxt)}" if nxt else ""
        return f"{series.summary}{when}"
    first = series.games[0]
    return f"Best of {series.best_of} · starts {_day(first)}"


def _card(series: Series) -> dict:
    return {"slug": series.slug, "href": mlb_bracket.series_href(series),
            "round": series.round_short, "round_name": series.round_name,
            "state": series.state, "status": _status(series),
            "sides": [_side(series, series.high), _side(series, series.low)]}


def _game_row(series: Series, game: Game, slugs: dict[str, str], hi_before: int,
              lo_before: int) -> dict:
    by_id = {series.high.team_id: series.high, series.low.team_id: series.low}
    away, home = by_id.get(game.away_id), by_id.get(game.home_id)
    away_name = away.label if away else "TBD"
    home_name = home.label if home else "TBD"
    after = ""
    if game.state == "final" and game.winner_id:
        hi = hi_before + (game.winner_id == series.high.team_id)
        lo = lo_before + (game.winner_id == series.low.team_id)
        after = mlb_bracket.standing_line(series, hi, lo)
    slug = slugs.get(game.game_id)
    return {
        "number": game.number, "day": _day(game), "time": _time(game),
        "start_utc": "" if game.time_tbd else utc_start_iso(game.start),
        "state": game.state, "status": game.status or "",
        "away": away_name, "home": home_name,
        "away_won": bool(game.winner_id and game.winner_id == game.away_id),
        "home_won": bool(game.winner_id and game.winner_id == game.home_id),
        "away_score": game.away_score, "home_score": game.home_score,
        "venue": game.venue if not game.placeholder else "",
        "pitchers": (f"{game.away_pitcher or 'TBD'} vs. {game.home_pitcher or 'TBD'}"
                     if game.state == "pre" and (game.away_pitcher or game.home_pitcher)
                     else ""),
        "if_necessary": game.if_necessary and game.state == "pre",
        "after": after,
        "matchup": f"/game/MLB/{game.game_id}/?day={slug}" if slug else "",
    }


def _rows(series: Series, slugs: dict[str, str]) -> list[dict]:
    rows, hi, lo = [], 0, 0
    shown = series.games if not series.winner else [g for g in series.games
                                                    if g.state == "final"]
    for game in shown:
        rows.append(_game_row(series, game, slugs, hi, lo))
        if game.winner_id == series.high.team_id:
            hi += 1
        elif game.winner_id == series.low.team_id:
            lo += 1
    return rows


def _read(bracket: Bracket) -> str:
    """One line on where the postseason is. Counts, never a forecast."""
    champ = bracket.champion
    if champ:
        return f"The {champ.name} won the {bracket.season} World Series."
    for order in (1, 2, 3, 4):
        this_round = [s for s in bracket.series if s.order == order]
        if not this_round or all(s.winner for s in this_round):
            continue
        decided = sum(1 for s in this_round if s.winner)
        name = mlb_bracket.ROUNDS[this_round[0].game_type][1]
        if not any(s.state != "upcoming" for s in this_round):
            first = min((g for s in this_round for g in s.games),
                        key=lambda g: g.official_date or "")
            return f"The {name} begins {_day(first)}."
        line = (f"{name}: {decided} of {len(this_round)} decided."
                if len(this_round) > 1 else f"{name} under way.")
        later = [s for s in bracket.series if s.order == order + 1]
        if later and not any(s.state != "upcoming" for s in later):
            first = min((g for s in later for g in s.games),
                        key=lambda g: g.official_date or "")
            nxt = mlb_bracket.ROUNDS[later[0].game_type][1]
            line += f" The {nxt} begins {_day(first)}."
        return line
    return ""


def _next_games(bracket: Bracket, slugs: dict[str, str]) -> list[dict]:
    """The next game of every series still being played, soonest first."""
    out = []
    for series in bracket.series:
        game = series.next_game
        if game is None or game.placeholder:
            continue
        info = mlb_bracket.game_in_series(bracket, game.game_id)
        row = _game_row(series, game, slugs, 0, 0)
        row.update({"round": series.round_short, "href": mlb_bracket.series_href(series),
                    "standing": "" if info.standing.startswith("Best of") else info.standing,
                    "stakes": info.stakes or "", "sort": game.start or ""})
        out.append(row)
    out.sort(key=lambda r: r["sort"])
    return out


def bracket_context(today: date) -> dict | None:
    bracket = mlb_bracket.load(today)
    if not mlb_bracket.is_active(bracket):
        return None
    slugs = matchup_slugs("MLB", today)
    columns = [{"title": title, "league": league or "MLB", "type": kind,
                "series": [_card(s) for s in bracket.round(kind, league)]}
               for kind, league, title in _COLUMNS]
    return {"section": "playoffs", "league": "MLB", "season": bracket.season,
            "columns": columns, "read": _read(bracket),
            "next_games": _next_games(bracket, slugs),
            "collected_at": _collected(bracket), "seeds_dropped": sorted(bracket.seeds_dropped),
            "champion": _side(next(s for s in bracket.series if s.game_type == "W"),
                              bracket.champion) if bracket.champion else None}


def _collected(bracket: Bracket) -> str:
    """"Sep 30, 9:14 AM PT" — when the bracket was last read from the source."""
    from components.format import PACIFIC

    try:
        stamp = datetime.fromisoformat(bracket.collected_at or "").astimezone(PACIFIC)
    except ValueError:
        return ""
    return stamp.strftime("%b %-d, %-I:%M %p PT")


# --- one series ------------------------------------------------------------------------

def _tape(bracket: Bracket, series: Series, today: date) -> list[dict]:
    """Regular-season facts about both clubs, side by side. Records, not ratings."""
    if not series.known:
        return []
    from services import standings

    table = standings.for_league("MLB", today)
    hi, lo = table.get(series.high.team_id), table.get(series.low.team_id)
    if not hi or not lo:
        return []
    rows = [
        ("Regular season", hi.record, lo.record),
        ("Division", hi.place or "—", lo.place or "—"),
        ("At home", hi.home_record or "—", lo.home_record or "—"),
        ("On the road", hi.road_record or "—", lo.road_record or "—"),
        ("Last 10", hi.last_ten or "—", lo.last_ten or "—"),
    ]
    return [{"label": label, "high": a, "low": b} for label, a, b in rows]


def _meetings(bracket: Bracket, series: Series) -> str:
    if not series.known:
        return ""
    record = bracket.meetings(series.high.team_id, series.low.team_id)
    if not record:
        return ""
    a, b = record.get(series.high.team_id, 0), record.get(series.low.team_id, 0)
    if not a and not b:
        return "The two clubs did not meet in the regular season."
    if a == b:
        return f"They split the regular-season series {a}-{b}."
    leader, x, y = ((series.high, a, b) if a > b else (series.low, b, a))
    return f"The {leader.short} won the regular-season series {x}-{y}."


def _road(bracket: Bracket, series: Series, side: Side, today: date) -> list[dict]:
    """How a club got here: the series it won, or the bye its seed earned."""
    if side.placeholder:
        if side.feeder:
            feeder = side.feeder
            text = f"Winner of the {feeder.round_name}, {feeder.matchup_short}"
            if not feeder.summary.startswith("Best of"):
                text += f" ({feeder.summary})"
            return [{"text": text, "href": mlb_bracket.series_href(feeder)}]
        return [{"text": "Decided by the earlier rounds.", "href": ""}]
    out = []
    entry = _entry(side, today)
    if entry:
        out.append({"text": entry, "href": ""})
    route = bracket.route(side.team_id, series)
    if side.seed in (1, 2) and not any(s.game_type == "F" for s, _ in route) \
            and series.order > 1:
        out.append({"text": "First-round bye", "href": ""})
    for won, beaten in route:
        score = f"{won.winner.wins}-{beaten.wins}"
        out.append({"text": f"Beat the {beaten.short} {score} in the {won.round_name}",
                    "href": mlb_bracket.series_href(won)})
    if not out and side.seed:
        out.append({"text": f"No. {side.seed} seed", "href": ""})
    return out


def _entry(side: Side, today: date) -> str:
    """How a club got into the field. MLB seeds division winners 1-3 and Wild Cards 4-6,
    so the seed says which, and the standings name the division."""
    if not side.seed:
        return ""
    from services import standings

    row = standings.for_league("MLB", today).get(side.team_id)
    record = f" at {row.record}" if row else ""
    if side.seed <= 3:
        division = row.division_short if row else None
        won = f"Won the {division}" if division else "Division winner"
        return f"{won}{record} · No. {side.seed} seed"
    league = (row.division_short or "").split(" ")[0] if row else ""
    wc = f"{league} Wild Card".strip()
    return f"{wc}{record} · No. {side.seed} seed"


def _next_round(bracket: Bracket, series: Series) -> dict | None:
    nxt = next((s for s in bracket.series if series in s.feeders), None)
    if nxt is None:
        return None
    other = next((side for side in (nxt.high, nxt.low)
                  if not side.placeholder and not series.side(side.team_id)), None)
    if series.winner:
        who = series.winner.short
        verb = "advanced" if nxt.state != "upcoming" else "advance"
        text = (f"The {who} {verb} to the {nxt.round_name}"
                + (f" against the {other.short}." if other else "."))
    else:
        text = (f"The winner plays in the {nxt.round_name}"
                + (f", against the {other.short}." if other else "."))
    return {"text": text, "href": mlb_bracket.series_href(nxt)}


def series_context(slug: str, today: date) -> dict | None:
    bracket = mlb_bracket.load(today)
    if not mlb_bracket.is_active(bracket):
        return None
    series = bracket.by_slug(slug)
    if series is None:
        return None
    slugs = matchup_slugs("MLB", today)
    nxt = series.next_game
    stakes = ""
    if nxt is not None and not nxt.placeholder:
        info = mlb_bracket.game_in_series(bracket, nxt.game_id)
        stakes = (info.stakes or "") if info else ""
    return {
        "section": "playoffs", "league": "MLB", "season": bracket.season,
        "series": _card(series), "best_of": series.best_of,
        "wins_needed": series.wins_needed,
        "summary": series.summary, "state": series.state, "stakes": stakes,
        "next_number": nxt.number if nxt else None,
        "games": _rows(series, slugs),
        "tape": _tape(bracket, series, today),
        "tape_names": (series.high.short, series.low.short),
        "meetings": _meetings(bracket, series),
        "roads": [{"name": s.label, "items": _road(bracket, series, s, today)}
                  for s in (series.high, series.low)],
        "next_round": _next_round(bracket, series),
        "collected_at": _collected(bracket),
    }
