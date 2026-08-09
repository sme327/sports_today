"""Evidence must not mislead — the wording is part of the product, not decoration.

Every case here comes from reading real props on a real slate and finding the text
said something softer, or plainly different, from what the numbers said. A score can
be defensible while the sentence next to it is not, and only the sentence is read.
"""

from __future__ import annotations

import pandas as pd

from services.mlb_analytics import match_pitcher
from src.pitcher_opportunity import _is_stale_window, _window_span_days


# --- negative evidence has to scale with severity -----------------------------

def _pa_rows(batter_id, hits_last25, *, pa_total=60, team="HOU"):
    """A batter with a controlled hit pattern: the oldest PA carry hits, the most
    recent 25 carry exactly ``hits_last25``."""
    rows = []
    older = pa_total - 25
    for i in range(older):
        rows.append({"is_hit": 1 if i % 3 == 0 else 0})
    for i in range(25):
        rows.append({"is_hit": 1 if i < hits_last25 else 0})
    out = []
    for i, r in enumerate(rows):
        out.append({
            "batter_id": batter_id, "batter_name": f"P{batter_id}", "batting_team": team,
            "game_id": f"g{i // 5}", "game_date": f"2026-08-{1 + i // 5:02d}",
            "pa_number": i, "is_hit": r["is_hit"], "reached_base": r["is_hit"],
            "is_strikeout": 0, "pitch_count_pa": 4, "is_official_ab": 1,
        })
    return out


def test_a_deep_slump_is_named_not_called_cooled():
    """Observed live: a batter with one hit in 25 plate appearances drew only
    "Recent hit rate has cooled" — the same words a mild dip gets."""
    from src.opportunity import score_hit_opportunities
    pa = pd.DataFrame(_pa_rows(1, hits_last25=1))
    out = score_hit_opportunities(pa, ["HOU"])
    risks = " ".join(out.iloc[0]["risks"])
    assert "1 hit in the last 25" in risks
    assert "cooled" not in risks.lower()


def test_an_ordinary_dip_still_reads_as_cooled():
    """The softer wording must survive for the case it was written for."""
    from src.opportunity import score_hit_opportunities
    pa = pd.DataFrame(_pa_rows(2, hits_last25=4))     # .160 — down, not a crisis
    out = score_hit_opportunities(pa, ["HOU"])
    risks = " ".join(out.iloc[0]["risks"])
    assert "cooled" in risks.lower() and "Ice cold" not in risks


# --- the WNBA last-5 hole ------------------------------------------------------

def _wnba_logs(player, values, threshold_metric="points"):
    rows = []
    for i, v in enumerate(values):
        rows.append({
            "player_id": player, "player_name": player, "team_id": "T", "team": "Team",
            "team_abbr": "TM", "headshot": None, "game_id": f"g{i}",
            "game_date": f"2026-08-{i + 1:02d}T00:00Z", "minutes": 32,
            "points": v if threshold_metric == "points" else 10,
            "rebounds": 5, "assists": 4, "started": 1,
            "three_pointers_made": 1, "field_goals_attempted": 10,
            "three_pointers_attempted": 4, "free_throws_attempted": 3, "turnovers": 2,
        })
    return pd.DataFrame(rows)


def test_dnp_rows_do_not_shrink_the_recent_window():
    """The bug this replaced a test for: DNPs were dropped *after* slicing, so five
    rows could collapse to a single game still described as "the last 5". A player
    who sat out four of five and scored 12 once in June was reported as
    average_l5 12.0 over a five-game sample."""
    from src.wnba_opportunity import score_wnba_opportunities
    values = [22] * 10 + [12]            # ten real games, then one older 12-point game
    logs = _wnba_logs("dnp", values)
    # Insert four did-not-play rows as the four most recent.
    dnp = _wnba_logs("dnp", [0, 0, 0, 0])
    dnp["game_date"] = ["2026-09-0%d T00:00Z".replace(" ", "") % i for i in range(1, 5)]
    dnp["points"] = [None] * 4
    dnp["minutes"] = [None] * 4
    logs = pd.concat([logs, dnp], ignore_index=True)
    out = score_wnba_opportunities(logs, ["Team"], max_per_player=3)
    assert not out.empty, "the player still has ten real games and must be scored"
    points = out[out["market"] == "points"]
    assert not points.empty
    row = points.iloc[0]
    # The window must describe played games, not roster rows: her five most recent
    # *appearances* all scored 22, so the average cannot be dragged toward the DNPs.
    assert row["average_l5"] == 20.0, row["average_l5"]   # [12,22,22,22,22], no DNPs
    assert row["minutes_l5"] == 32.0, row["minutes_l5"]


def test_a_traded_player_is_not_offered_for_their_old_team():
    """Kelsey Plum moved Sparks -> Mercury in July and was still being offered in a
    Sparks game, scored on her stale Sparks games. Eligibility follows the team of
    the player's most recent appearance."""
    from src.wnba_opportunity import score_wnba_opportunities
    old = _wnba_logs("mover", [20] * 8)
    old["team"] = "Los Angeles Sparks"
    old["team_abbr"] = "LA"
    new_club = _wnba_logs("mover", [22, 21, 20])
    new_club["team"] = "Phoenix Mercury"
    new_club["team_abbr"] = "PHX"
    new_club["game_date"] = ["2026-09-01T00:00Z", "2026-09-02T00:00Z", "2026-09-03T00:00Z"]
    logs = pd.concat([old, new_club], ignore_index=True)

    assert score_wnba_opportunities(logs, ["Los Angeles Sparks"]).empty
    assert not score_wnba_opportunities(logs, ["Phoenix Mercury"]).empty


def test_a_traded_players_form_travels_with_them():
    """Scored for the new club, but on all their recent games — form does not reset
    at a transfer, only eligibility does."""
    from src.wnba_opportunity import score_wnba_opportunities
    old = _wnba_logs("mover2", [20] * 8)
    old["team"], old["team_abbr"] = "Los Angeles Sparks", "LA"
    new_club = _wnba_logs("mover2", [22, 21, 20])
    new_club["team"], new_club["team_abbr"] = "Phoenix Mercury", "PHX"
    new_club["game_date"] = ["2026-09-01T00:00Z", "2026-09-02T00:00Z", "2026-09-03T00:00Z"]
    out = score_wnba_opportunities(pd.concat([old, new_club], ignore_index=True), ["Phoenix Mercury"])
    assert not out.empty
    # 11 games of form, not just the 3 for the new club.
    assert out.iloc[0]["stability_score"] > 45


def test_a_poor_recent_rate_is_never_called_no_red_flags():
    """The false reassurance: "No standout red flags in recent form" appeared on
    props the player had missed in three of her last five."""
    from src.wnba_opportunity import score_wnba_opportunities
    logs = _wnba_logs("mixed", [16] * 10 + [16, 9, 9, 16, 9])
    out = score_wnba_opportunities(logs, ["Team"])
    for _, row in out.iterrows():
        risks = " ".join(row["risks"])
        if "only" in risks or "any of the last 5" in risks:
            assert "No standout red flags" not in risks


# --- names ---------------------------------------------------------------------

def _pitcher_frame(pairs):
    return pd.DataFrame([{"pitcher_name": n, "pitcher_id": i} for n, i in pairs])


def test_accented_names_match_the_unaccented_feed():
    """The schedule says "Randy Vásquez", the vendor feed stores "Randy Vasquez".
    Exact matching returned None and that pitcher silently lost every prop — 2 of 30
    probables on the slate this was found on."""
    pa = _pitcher_frame([("Randy Vasquez", 681190), ("Jesus Luzardo", 666200)])
    assert match_pitcher(pa, "Randy Vásquez") == "681190"
    assert match_pitcher(pa, "Jesús Luzardo") == "666200"
    assert match_pitcher(pa, "Randy Vasquez") == "681190"     # unaccented still works


def test_an_ambiguous_name_matches_nobody():
    """Two players sharing a name (the feed currently has two Max Muncys) must not
    resolve to whichever row happens to come first — showing no prop beats silently
    scoring the wrong player. CLAUDE.md: never join on names."""
    pa = _pitcher_frame([("Luis Garcia", 1), ("Luis Garcia", 2)])
    assert match_pitcher(pa, "Luis Garcia") is None


def test_an_unknown_name_matches_nobody():
    assert match_pitcher(_pitcher_frame([("A B", 1)]), "Nobody Here") is None


# --- stale start windows --------------------------------------------------------

def test_window_span_is_measured_in_days():
    assert _window_span_days(["2026-08-03", "2026-07-12", "2026-04-03"]) == 122
    assert _window_span_days(["2026-08-03"]) is None      # one start spans nothing


def test_starts_spread_across_months_are_flagged_stale():
    """A rotation turns over every ~5 days, so four starts should span ~20. Observed
    live: 128 days across a three-month absence, scored 95."""
    assert _is_stale_window(128, 4)
    assert _is_stale_window(60, 4)


def test_a_normal_rotation_window_is_not_flagged():
    assert not _is_stale_window(20, 4)      # four starts, every five days
    assert not _is_stale_window(30, 6)
    assert not _is_stale_window(None, 4)    # undatable — no claim either way


def test_every_offered_prop_states_how_often_the_bar_is_cleared():
    """The clear rate is the most important number about a prop and was shown only
    at the extremes — strong (L5>=.8 / L10>=.7) or poor (L5<=.4). Props resting
    exactly on the MIN_CLEAR floor therefore disclosed nothing: 6 of 19 on the slate
    this was found on, every one at .60/.60, including one scored 67."""
    from src.wnba_opportunity import score_wnba_opportunities
    # Six of ten clear 15 — exactly the qualifying floor, previously silent.
    logs = _wnba_logs("floor", [16, 9, 16, 9, 16, 16, 9, 16, 9, 16])
    out = score_wnba_opportunities(logs, ["Team"], max_per_player=3)
    points = out[out["market"] == "points"]
    assert not points.empty
    lines = list(points.iloc[0]["support"]) + list(points.iloc[0]["risks"])
    assert any("Cleared" in line for line in lines), lines


def test_a_weak_recent_run_shows_both_the_baseline_and_the_warning():
    """A prop can qualify on its ten-game rate while its last five are poor; the
    reader needs both numbers, not whichever one the code reached first."""
    from src.wnba_opportunity import score_wnba_opportunities
    # Strong older games, weak recent five: L10 clears the floor, L5 does not.
    logs = _wnba_logs("split", [16] * 5 + [16, 9, 9, 16, 9])
    out = score_wnba_opportunities(logs, ["Team"], max_per_player=3)
    points = out[out["market"] == "points"]
    if not points.empty:
        support = " ".join(points.iloc[0]["support"])
        risks = " ".join(points.iloc[0]["risks"])
        assert "Cleared" in support
        assert "only" in risks
