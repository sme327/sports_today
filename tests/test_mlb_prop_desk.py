"""The postseason prop desk, written as the ways it could mislead.

Each test names a rule from the spec (decision log 2026-09-30): the phases are never
pooled, small samples are counts, the lineup's state is never overstated, and the surface
never turns evidence into a verdict. Synthetic plate appearances; no network.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from services import mlb_prop_desk as D
from services.data_access import is_postseason, load_plate_appearances

REG, POST = "MLB 2026 Regular Season", "MLB 2026 Postseason"
CUBS, PADRES, DODGERS = "Chicago Cubs", "San Diego Padres", "Los Angeles Dodgers"


def _pa(game_id, day, batting, pitching, batter, pitcher, *, dataset=REG, hit=0, tb=0,
        k=0, bb=0, inning="1T", pitches=4, outs=1, n=1, hand="R", phand="R"):
    return {
        "dataset": dataset, "game_id": game_id, "game_date": pd.Timestamp(day),
        "inning": inning, "batting_team": batting, "pitching_team": pitching,
        "batter_id": batter, "batter_name": f"Batter {batter}", "batter_hand": hand,
        "pitcher_id": pitcher, "pitcher_name": f"Pitcher {pitcher}", "pitcher_hand": phand,
        "pitch_count_pa": pitches, "outs_on_play": outs, "is_hit": hit, "total_bases": tb,
        "is_walk": bb, "is_strikeout": k, "is_official_ab": 0 if bb else 1, "pa_number": n,
    }


def _game(game_id, day, batting, pitching, lineup, pitcher, *, dataset=REG, hits=None,
          ks=None, inning="1T"):
    """One team's nine batters, one PA each, in order, against one pitcher."""
    hits, ks = hits or {}, ks or {}
    return [_pa(game_id, day, batting, pitching, b, pitcher, dataset=dataset,
                hit=1 if hits.get(b) else 0, tb=hits.get(b, 0), k=1 if ks.get(b) else 0,
                n=i, inning=inning)
            for i, b in enumerate(lineup, 1)]


CUBS_NINE = [101, 102, 103, 104, 105, 106, 107, 108, 109]
PADRES_NINE = [201, 202, 203, 204, 205, 206, 207, 208, 209]


def _season() -> pd.DataFrame:
    rows = []
    # Regular season: Cubs bat against Padres starter 900 and Dodgers starter 950;
    # batter 101 has a hit in every regular-season game.
    for i, day in enumerate(["2026-09-01", "2026-09-10", "2026-09-20", "2026-09-27"]):
        rows += _game(1000 + i, day, CUBS, PADRES if i % 2 else DODGERS, CUBS_NINE,
                      900 if i % 2 else 950, hits={101: 1}, ks={102: 1})
        rows += _game(1100 + i, day, PADRES, CUBS, PADRES_NINE, 800)
        # A second time through, so 800 and 900 clear the ten-batter start bar.
        rows += _game(1100 + i, day, PADRES, CUBS, PADRES_NINE, 800, inning="2T")
    rows += _game(1001, "2026-09-10", CUBS, PADRES, CUBS_NINE, 900, inning="2T")
    rows += _game(1003, "2026-09-27", CUBS, PADRES, CUBS_NINE, 900, inning="2T")
    # Postseason Game 1: 101 goes hitless and strikes out; the Cubs bat in a new order.
    reordered = [103, 101, 102, 104, 105, 106, 107, 108, 109]
    rows += _game(2000, "2026-09-29", CUBS, PADRES, reordered, 900, dataset=POST,
                  ks={101: 1})
    rows += _game(2000, "2026-09-29", CUBS, PADRES, reordered, 900, dataset=POST,
                  inning="2T")
    rows += _game(2000, "2026-09-29", PADRES, CUBS, PADRES_NINE, 800, dataset=POST)
    return pd.DataFrame(rows)


def _desk(pa=None, lineups=None):
    return D.build(_season() if pa is None else pa, away_team=CUBS, home_team=PADRES,
                   away_short="Cubs", home_short="Padres", away_pid="800",
                   home_pid="900", lineups=lineups)


def _hitter(desk, pid):
    return next(h for side in (desk.away, desk.home) for h in side.hitters if h.pid == pid)


# --- the phases are never pooled -----------------------------------------------------

def test_postseason_rows_are_identified_by_the_feeds_dataset():
    pa = _season()
    assert is_postseason(pa).sum() == 27
    assert not is_postseason(pa[pa["dataset"] == REG]).any()


def test_the_loader_can_return_one_phase(tmp_path):
    import sqlite3

    db = tmp_path / "t.db"
    with sqlite3.connect(db) as conn:
        _season().assign(game_date=lambda d: d["game_date"].dt.strftime("%Y-%m-%d")) \
            .to_sql("plate_appearances", conn, index=False)
    regular = load_plate_appearances(db_path=db, phase="regular")
    post = load_plate_appearances(db_path=db, phase="postseason")
    both = load_plate_appearances(db_path=db)
    assert len(regular) + len(post) == len(both) and len(post) == 27
    assert not is_postseason(regular).any()


def test_the_season_baseline_never_includes_a_playoff_game():
    batter = _hitter(_desk(), "101")
    season, post = batter.slices["season"], batter.slices["post"]
    assert season.games == 4 and season.clears("h", 1).hit == 4
    assert post.games == 1 and post.h == 0 and post.k == 1


def test_recent_windows_are_the_last_days_of_the_regular_season():
    desk = _desk()
    assert desk.reg_end == date(2026, 9, 27)
    assert desk.data_through == date(2026, 9, 29)
    l14 = _hitter(desk, "101").slices["l14"]
    # Sep 14-27: the Sep 20 and Sep 27 games, and not the Sep 29 playoff game.
    assert l14.span == "Sep 14–27" and l14.games == 2


def test_the_series_is_this_postseason_against_tonights_opponent_only():
    batter = _hitter(_desk(), "101")
    assert batter.slices["series"].games == 1
    assert batter.slices["opp"].games == 2          # regular season vs the Padres
    assert batter.slices["opp"].span == "regular season"


# --- small samples are counts ---------------------------------------------------------

def test_a_small_sample_is_a_count_never_a_bare_rate():
    assert D.Count(3, 4).text == "3/4"
    assert D.Count(12, 20).text == "12/20 · 60%"
    assert D.Count(0, 0).text == "—"


def test_batter_vs_pitcher_is_raw_counts():
    batter = _hitter(_desk(), "102")
    # 102 faced 900 in two regular-season games (two PA each) and Game 1 (two PA).
    assert batter.bvp.pa == 6
    assert batter.bvp_line.endswith("in 6 PA")
    assert "%" not in batter.bvp_line


# --- lineups --------------------------------------------------------------------------

def test_an_unposted_lineup_is_last_games_order_and_says_so():
    desk = _desk()
    assert not desk.away.confirmed
    assert "not tonight's" in desk.away.source
    # The most recent game is the postseason opener, where 103 led off.
    assert [h.pid for h in desk.away.hitters][:2] == ["103", "101"]


def test_a_posted_lineup_is_used_in_its_own_order():
    from src.mlb_lineups import Lineups

    order = tuple((pid, f"Batter {pid}") for pid in reversed(CUBS_NINE))
    lineups = Lineups(slot={}, posted_teams=frozenset({CUBS}), order={CUBS: order})
    desk = _desk(lineups=lineups)
    assert desk.away.confirmed and desk.away.source == "Confirmed lineup"
    assert desk.away.hitters[0].pid == "109" and desk.away.hitters[0].slot == 1


def test_the_lineup_parser_keeps_the_batting_order():
    from src.mlb_lineups import _parse

    players = [{"id": 600 + i, "fullName": f"P{i}"} for i in range(9)]
    payload = {"dates": [{"games": [{
        "teams": {"away": {"team": {"name": CUBS}}, "home": {"team": {"name": PADRES}}},
        "lineups": {"awayPlayers": players, "homePlayers": players[:5]}}]}]}
    parsed = _parse(payload)
    assert parsed.order[CUBS][0] == (600, "P0") and len(parsed.order[CUBS]) == 9
    assert PADRES not in parsed.order          # five names is not a posted lineup


# --- starters -------------------------------------------------------------------------

def test_starter_workload_and_strips_come_from_regular_season_starts():
    sp = _desk().home.starter                  # 900, the Padres' starter
    assert sp.starts == 2                      # the two games he went past ten batters
    assert sp.avg["bf"] == 18.0 and sp.avg["pitches"] == 72.0
    assert [o.bf for o in sp.recent] == [18, 18]
    assert sp.recent[0].ip == "6.0"
    assert len(sp.post) == 1 and sp.post[0].start


def test_starter_thresholds_count_each_way():
    sp = _desk().home.starter
    season_4k = next(row for row in sp.thresholds["sk"] if row[0] == "4+ K")[1]
    assert (season_4k.hit, season_4k.n) == (0, 2)
    walks = dict((row[0], row[1]) for row in sp.thresholds["bb"])
    assert walks["1 or fewer"].hit == 2 and walks["3+"].hit == 0


def test_the_opposing_lineup_profile_is_against_the_starters_hand():
    sp = _desk().home.starter
    assert sp.lineup["k"].n > 0
    assert "vs RHP, regular season" in sp.lineup_note


# --- the surface never makes the decision ---------------------------------------------

def test_the_desk_renders_every_mode_with_its_note():
    from components.prop_desk import prop_desk_html

    html = prop_desk_html(_desk())
    for key, _label in D.MODES:
        assert f'data-mode="{key}"' in html
        assert f'class="pd-note" data-m="{key}"' in html
    assert "Playoff Prop Desk" in html and "Data through Sep 29" in html
    assert 'data-pd-modes hidden' in html      # controls wait for the script


def test_the_desk_uses_no_verdict_language_or_colour():
    from components.prop_desk import prop_desk_html

    import re

    html = prop_desk_html(_desk()).lower()
    text = re.sub(r"<[^>]+>", " ", html)            # what a reader sees
    for word in ("strong", "weak", "best bet", "confidence", "positioned",
                 "lock", "edge", "probability"):
        assert word not in text, word
    # Colour arrives through classes; none of them may be the site's support/risk pair.
    classes = " ".join(re.findall(r'class="([^"]*)"', html))
    for colour in ("green", "red", "coral", "support", "risk", "good", "bad"):
        assert colour not in classes.split(), colour
    assert "style=" not in html


def test_the_desk_appears_only_on_postseason_games():
    from domain.models import SlateGame
    from web.games import _prop_desk

    regular = SlateGame(league="MLB", game_id="1", phase="regular")
    assert _prop_desk(regular, date(2026, 9, 30)) == ""


# --- found by the QC against MLB's own game logs (2026-09-30) ---------------------------

def _with_steal():
    """Batter 201 singles; 202's at-bat is interrupted by a steal (an event row carrying
    the pitch count so far), then completes; 203's at-bat ends the inning on a caught
    stealing before it finishes."""
    rows = [
        _pa(1, "2026-09-01", PADRES, CUBS, 201, 800, hit=1, tb=1, pitches=3, outs=0),
        {**_pa(1, "2026-09-01", PADRES, CUBS, 202, 800, pitches=2, outs=0), "play_type": ""},
        _pa(1, "2026-09-01", PADRES, CUBS, 202, 800, k=1, pitches=5, outs=1),
        _pa(1, "2026-09-01", PADRES, CUBS, 204, 800, pitches=4, outs=1),
        {**_pa(1, "2026-09-01", PADRES, CUBS, 203, 800, pitches=2, outs=1), "play_type": ""},
    ]
    for r in rows:
        r.setdefault("play_type", "SINGLE")
    return pd.DataFrame(rows)


def test_running_events_are_not_plate_appearances():
    games = D.batter_games(_with_steal().assign(batter_id=lambda d: d["batter_id"].astype(str)))
    assert games.loc[games["batter_id"] == "202", "pa"].item() == 1
    assert "203" not in set(games["batter_id"])        # never completed an at-bat


def test_a_starters_workload_counts_each_at_bat_once_and_every_out():
    apps = D.pitcher_appearances(_with_steal())
    row = apps.iloc[0]
    assert row["bf"] == 3                     # 201, 202, 204 — not the steal rows
    assert row["pitches"] == 3 + 5 + 4 + 2    # 202's interrupted count dropped; 203's kept
    assert row["outs"] == 3                   # the caught stealing is his out too
    assert bool(row["start"])


def test_a_short_start_is_still_a_start():
    # Four batters and out: an early exit is exactly what a strikeout line needs to see.
    assert bool(D.pitcher_appearances(_with_steal()).iloc[0]["start"])


def test_starts_separated_by_a_long_gap_state_their_span():
    sp = _desk().home.starter
    gapped = D.Starter(**{**sp.__dict__, "recent_dates": (date(2026, 4, 1), date(2026, 4, 7),
                                                           date(2026, 9, 7), date(2026, 9, 13))})
    assert gapped.recent_span == "Apr 1 – Sep 13"
    assert gapped.gap_before == {2}
    tight = D.Starter(**{**sp.__dict__, "recent_dates": (date(2026, 9, 1), date(2026, 9, 7))})
    assert tight.recent_span is None


def test_estimated_workload_is_marked_and_the_lineup_state_is_unmissable():
    from components.prop_desk import prop_desk_html

    html = prop_desk_html(_desk())
    assert "Pitches ~" in html and "Innings ~" in html and "Batters faced ~" not in html
    assert "Not confirmed" in html
    assert "last game&#x27;s order (Sep 29), not tonight&#x27;s" in html
    assert "\\" not in html                  # no stray escapes reach the page
