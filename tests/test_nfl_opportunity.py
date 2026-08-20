"""Offline tests for NFL player-prop selection (reachable-bar, by position)."""

from __future__ import annotations

import pandas as pd

from src.nfl_opportunity import best_prop, key_players


def _games(position, **stat_vals):
    """Build a player's game log from lists of per-game stat values."""
    n = len(next(iter(stat_vals.values())))
    rows = []
    for i in range(n):
        row = {"game_date": f"2025-09-{i + 1:02d}", "player_id": "p1", "player": "Player One",
               "position": position}
        for stat, vals in stat_vals.items():
            row[stat] = vals[i]
        rows.append(row)
    return pd.DataFrame(rows)


def test_best_prop_picks_highest_reachable_bar():
    rb = _games("RB", rushing_yds=[80, 90, 50, 70, 65, 85])   # 60+ in 5/6, 75+ in only 3/6
    prop = best_prop(rb, "RB")
    assert prop is not None
    assert prop["stat"] == "rushing_yds" and prop["threshold"] == 60
    assert prop["label"] == "Rush Yards" and prop["clear_rate"] >= 0.55


def test_best_prop_needs_enough_games():
    assert best_prop(_games("RB", rushing_yds=[80, 90, 70]), "RB") is None   # 3 < MIN_GAMES


def test_best_prop_none_when_no_reachable_bar():
    # A low-volume receiver clears no meaningful bar in ≥55% of games.
    wr = _games("WR", receiving_yds=[10, 0, 20, 5, 15, 8])
    assert best_prop(wr, "WR") is None


def test_key_players_picks_qb_rb_and_receivers():
    df = pd.DataFrame([
        {"player_id": "qb", "player": "QB", "position": "QB", "passing_att": 34,
         "rushing_att": 3, "receiving_tar": 0},
        {"player_id": "rb", "player": "RB", "position": "RB", "passing_att": 0,
         "rushing_att": 18, "receiving_tar": 2},
        {"player_id": "wr1", "player": "WR1", "position": "WR", "passing_att": 0,
         "rushing_att": 0, "receiving_tar": 9},
        {"player_id": "wr2", "player": "WR2", "position": "WR", "passing_att": 0,
         "rushing_att": 0, "receiving_tar": 6},
        {"player_id": "wr3", "player": "WR3", "position": "WR", "passing_att": 0,
         "rushing_att": 0, "receiving_tar": 1},   # too few targets → excluded
    ])
    ids = {p[0] for p in key_players(df)}
    assert {"qb", "rb", "wr1", "wr2"} <= ids and "wr3" not in ids


# --- slate scoring + registry (2026-08-18) ------------------------------------------

def _slate_games(stat, values, player="P1", team="Team A", position="WR"):
    import pandas as pd
    return pd.DataFrame([{
        "player_id": player.lower(), "player": player, "team": team,
        "position": position, "game_date": f"2025-09-{10 + i:02d}", stat: v,
    } for i, v in enumerate(values)])


def test_a_player_is_scored_in_every_market_they_reach_not_just_their_position():
    """`best_prop` picks one prop for a spotlight; the slate wants the population. A
    receiving back is a genuine receptions prop and a running QB is a rush-attempts
    prop, so scoring only the position's primary stat would drop real props."""

    from src.nfl_opportunity import score_nfl_opportunities
    frame = _slate_games("receiving_yds", [55, 62, 71, 48, 90], position="RB")
    frame["receiving_rec"] = [5, 6, 5, 4, 7]
    frame["rushing_att"] = [12, 15, 11, 14, 13]
    keys = set(score_nfl_opportunities(frame).market_key)
    assert {"nfl_rec_yds", "nfl_receptions", "nfl_rush_att"} <= keys


def test_a_bar_the_player_rarely_clears_is_never_offered():
    """The reachable-bar discipline, which is what earns the lift: a player is only
    offered a bar they clear in at least 55% of recent games."""
    from src.nfl_opportunity import score_nfl_opportunities
    # 40 yards is the lowest bar; this player clears it twice in six games.
    scored = score_nfl_opportunities(_slate_games("receiving_yds", [12, 8, 45, 15, 60, 9]))
    assert scored.empty


def test_the_recent_line_is_oldest_first_and_matches_the_bar():
    from src.nfl_opportunity import score_nfl_opportunities
    scored = score_nfl_opportunities(_slate_games("receiving_rec", [4, 5, 6, 4, 7]))
    row = scored.iloc[0]
    assert row.recent_line == [4.0, 5.0, 6.0, 4.0, 7.0], "left-to-right must read as time"
    assert row.threshold <= min(row.recent_line) or row.clear_rate >= 0.55


def test_risks_name_role_volatility_rather_than_form():
    """Football's hazard is that a *role* vanishes between weeks — injury, game script, a
    committee backfield — in a way a baseball lineup slot does not."""
    from src.nfl_opportunity import score_nfl_opportunities
    scored = score_nfl_opportunities(_slate_games("receiving_rec", [8, 9, 7, 2, 1]))
    risks = " ".join(scored.iloc[0].risks).lower()
    assert "last 3" in risks or "swung widely" in risks or "role" in risks


def test_every_nfl_market_is_registered_and_gradeable():
    """A scorer emitting a market the registry does not know would be scored, shown, and
    then silently never graded."""
    from domain.markets import MARKETS, NFL_STAT_COLUMN
    from src.nfl_opportunity import _SCORED_MARKETS

    for key in _SCORED_MARKETS:
        assert key in MARKETS, f"{key} is scored but not registered"
        assert key in NFL_STAT_COLUMN, f"{key} has no column to grade against"
        assert MARKETS[key].league == "NFL"


def test_nfl_markets_are_over_only():
    """An "under 4 receptions" prop is a bet on absence — the shape that made SP
    hits-allowed unders carry no information (-0.011 lift over 189 graded rows)."""
    from domain.markets import MARKETS
    for key, spec in MARKETS.items():
        if spec.league == "NFL":
            assert not spec.allows_both, f"{key} must not offer an under"


def test_props_go_quiet_when_the_ingested_feed_is_months_old():
    """An NFL offseason is seven months of trades, retirements and depth-chart churn.
    Scoring an August preseason game off January's games produced a confident-looking
    "Tony Pollard 10+ carries" for a back who may not be on that roster — exactly the
    failure the honest-data rule exists to prevent. Silence beats a stale number."""
    import pandas as pd
    from datetime import date

    from leagues.nfl.adapter import _is_stale

    january = pd.DataFrame({"game_date": ["2026-01-12"]})
    assert _is_stale(january, date(2026, 8, 18)), "7 months stale must be refused"
    assert not _is_stale(january, date(2026, 1, 18)), "a week later is current"
    # A late vendor feed mid-season must not silence the slate.
    assert not _is_stale(january, date(2026, 2, 10)), "4 weeks is a bye, not an offseason"
    assert _is_stale(pd.DataFrame(), date(2026, 9, 1)), "no data is stale by definition"
    assert _is_stale(pd.DataFrame({"game_date": ["not-a-date"]}), date(2026, 9, 1))


# --- traded players (2026-08-19) ----------------------------------------------------

def _traded(stat, old_values, new_values, old_team="Old Team", new_team="New Team"):
    """One player, one season boundary, two teams — the shape a trade actually makes."""
    rows = [{"player_id": "p1", "player": "P1", "team": old_team, "position": "TE",
             "season": 2024, "game_date": f"2024-11-{10 + i:02d}", stat: v}
            for i, v in enumerate(old_values)]
    rows += [{"player_id": "p1", "player": "P1", "team": new_team, "position": "TE",
              "season": 2025, "game_date": f"2025-09-{10 + i:02d}", stat: v}
             for i, v in enumerate(new_values)]
    return pd.DataFrame(rows)


def test_a_traded_player_keeps_the_history_he_earned_elsewhere():
    """Grouping on team once split a traded player into per-team fragments, so his prior
    season vanished and he fell under the games floor. At week 3 of 2025 that cost 459
    players their track record — Aaron Rodgers had 20 games played and 2 under his
    current team, so he was offered no prop at all."""
    from src.nfl_opportunity import score_nfl_opportunities

    scored = score_nfl_opportunities(_traded("receiving_yds", [55, 62, 71, 48, 90], [60]))
    assert not scored.empty, "a traded player must keep his history"
    assert int(scored.iloc[0]["games"]) == 6


def test_a_traded_player_is_shown_under_the_team_he_plays_for_now():
    from src.nfl_opportunity import score_nfl_opportunities

    scored = score_nfl_opportunities(_traded("receiving_yds", [55, 62, 71, 48, 90], [60]))
    assert set(scored["team"]) == {"New Team"}


def test_the_team_filter_follows_the_player_not_his_old_games():
    """A slate lists today's teams. Filtering rows by team kept a traded player's *old*
    games and dropped the team he now plays for — the wrong half of his career."""
    from src.nfl_opportunity import score_nfl_opportunities

    frame = _traded("receiving_yds", [55, 62, 71, 48, 90], [60])
    assert not score_nfl_opportunities(frame, teams=["New Team"]).empty
    assert score_nfl_opportunities(frame, teams=["Old Team"]).empty


def test_prior_season_games_are_disclosed_for_a_traded_player():
    """The disclosure existed but could never fire for a traded player: each per-team
    fragment was internally single-season, so nothing looked stale."""
    from src.nfl_opportunity import score_nfl_opportunities

    scored = score_nfl_opportunities(_traded("receiving_yds", [55, 62, 71, 48, 90], [60]))
    assert any("5 of these 6 games are from last season" in r
               for r in scored.iloc[0]["risks"])
