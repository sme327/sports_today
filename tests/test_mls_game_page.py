"""Offline tests for the MLS matchup page. No network; synthetic SlateGames.

Covers the parser, the builder's real-data paths (record/form/points/storylines),
and the honesty invariants: sections without a data pipeline stay UNAVAILABLE,
and no fabricated numbers leak into placeholder rows.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from components import mls_game as C
from domain.mls_game_page import DataState
from domain.models import SlateGame
from services.mls_game_page import (
    _parse_record, _points, _win_pct, _form_tuple, build_mls_game_page,
)
from src import espn_soccer


# --------------------------------------------------------------- fixtures ----
def _game(away_rec="3-2-9", home_rec="10-3-1",
          away_form=("L", "L", "D", "L", "W"), home_form=("W", "W", "W", "D", "L"),
          state="pre", away_score=None, home_score=None) -> SlateGame:
    return SlateGame(
        league="MLS", game_id="761663",
        start_time=datetime(2026, 7, 17, 23, 30, tzinfo=timezone.utc),
        away_name="Atlanta United FC", home_name="Nashville SC",
        away_short="Atlanta", home_short="Nashville",
        away_abbr="ATL", home_abbr="NSH",
        away_logo="https://a.espncdn.com/x.png", home_logo="https://a.espncdn.com/y.png",
        venue="GEODIS Park", away_score=away_score, home_score=home_score, state=state,
        status_detail="Final" if state == "final" else "Scheduled",
        meta={
            "competition": "MLS Regular Season", "broadcast": "Apple TV",
            "away_record": away_rec, "home_record": home_rec,
            "away_form": away_form, "home_form": home_form,
            "away_color": "#9d2235", "home_color": "#ece83a",
        },
    )


def _build(**kw):
    g = _game(**kw)
    return build_mls_game_page(g, date(2026, 7, 17), date(2026, 7, 17))


# --------------------------------------------------------------- parser ------
def test_parse_espn_soccer_payload():
    payload = {"events": [{
        "id": "1", "date": "2026-07-17T23:30Z", "season": {"slug": "regular-season"},
        "status": {"type": {"state": "pre", "detail": "Scheduled", "shortDetail": "Sched"}},
        "competitions": [{
            "venue": {"fullName": "GEODIS Park"},
            "broadcasts": [{"names": ["Apple TV"]}],
            "competitors": [
                {"homeAway": "home", "score": "0", "form": "WWWDL",
                 "records": [{"type": "total", "summary": "10-3-1"}],
                 "team": {"displayName": "Nashville SC", "shortDisplayName": "Nashville",
                          "abbreviation": "NSH", "logo": "y.png", "color": "ece83a"}},
                {"homeAway": "away", "score": "0", "form": "LLDLW",
                 "records": [{"type": "total", "summary": "3-2-9"}],
                 "team": {"displayName": "Atlanta United FC", "shortDisplayName": "Atlanta",
                          "abbreviation": "ATL", "logo": "x.png", "color": "9d2235"}},
            ],
        }],
    }]}
    games = espn_soccer.parse(payload, espn_soccer.MLS)
    assert len(games) == 1
    g = games[0]
    assert g["home"] == "Nashville SC" and g["away"] == "Atlanta United FC"
    assert g["home_record"] == "10-3-1" and g["away_form"] == ("L", "L", "D", "L", "W")
    assert g["home_color"] == "#ece83a"
    assert g["competition"] == "MLS Regular Season" and g["state"] == "pre"


def test_record_helpers():
    assert _parse_record("10-3-1") == (10, 3, 1)
    assert _parse_record("bad") is None and _parse_record(None) is None
    assert _points("10-3-1") == 33            # 10*3 + 3
    assert _win_pct("10-3-1") == pytest.approx(10 / 14)
    assert _form_tuple("WDL") == ("W", "D", "L")
    assert _form_tuple(["W", "d", "x", "L"]) == ("W", "D", "L")  # list + junk filtered


# --------------------------------------------------------------- hero --------
def test_hero_is_real_data():
    p = _build()
    assert p.hero.away.short == "Atlanta" and p.hero.home.short == "Nashville"
    assert p.hero.home.points_display == "33 pts"
    assert p.hero.away.form == ("L", "L", "D", "L", "W")
    assert p.hero.competition == "MLS Regular Season"
    assert p.hero.venue == "GEODIS Park"


def test_hero_handles_json_roundtripped_form_lists():
    # schedule_cache serializes tuples to lists; the builder must accept lists.
    p = _build(home_form=["W", "W", "W", "D", "L"])
    assert p.hero.home.form == ("W", "W", "W", "D", "L")


# ----------------------------------------------------------- snapshot --------
def test_snapshot_partial_real_rows_and_honest_placeholders():
    p = _build()
    assert p.snapshot.state is DataState.PARTIAL
    by_label = {r.label: r for r in p.snapshot.rows}
    assert by_label["Record"].state is DataState.AVAILABLE
    assert by_label["Points"].better == "home"         # 33 > 11
    # Placeholder rows must be UNAVAILABLE and carry no fabricated value.
    for lbl in ("Goals / match", "Possession", "Shots on target"):
        assert by_label[lbl].state is DataState.UNAVAILABLE
        assert by_label[lbl].away_value == "—" and by_label[lbl].home_value == "—"


# ---------------------------------------------------------- storylines -------
def test_storylines_from_real_record_and_form():
    p = _build()  # 3-2-9 vs 10-3-1, Nashville 3W in last 5
    assert p.storylines.state is DataState.AVAILABLE
    titles = " | ".join(s.title for s in p.storylines.items)
    assert "stronger side on paper" in titles       # record contrast triggers
    assert any("form" in s.title for s in p.storylines.items)
    # Every storyline is evidence-backed.
    assert all(s.evidence for s in p.storylines.items)
    assert len(p.storylines.items) <= 3


def test_storylines_absent_when_records_even_and_form_mixed():
    p = _build(away_rec="5-5-5", home_rec="5-5-5",
               away_form=("W", "L", "W", "L", "D"), home_form=("D", "W", "L", "W", "L"))
    assert p.storylines.state is DataState.UNAVAILABLE
    assert p.storylines.items == ()


def test_storyline_counts_are_order_independent():
    # Same W/D/L counts, different order → same "in form" conclusion (3 wins).
    a = _build(home_form=("W", "W", "W", "D", "L"))
    b = _build(home_form=("L", "D", "W", "W", "W"))
    a_titles = {s.title for s in a.storylines.items}
    b_titles = {s.title for s in b.storylines.items}
    assert a_titles == b_titles


# ------------------------------------------------ honesty invariants ---------
def test_analytical_sections_are_honestly_unavailable():
    p = _build()
    assert p.tactical.state is DataState.UNAVAILABLE
    assert p.lineups.state is DataState.UNAVAILABLE
    assert p.players.state is DataState.UNAVAILABLE
    assert p.attacking.state is DataState.UNAVAILABLE
    assert p.discipline.state is DataState.UNAVAILABLE
    # Timeline is generic, clearly-labeled guidance → available.
    assert p.timeline.state is DataState.AVAILABLE
    assert len(p.timeline.phases) == 6


def test_no_player_names_invented():
    p = _build()
    assert all(a.player is None for a in p.players.archetypes)
    for lu in (p.lineups.away, p.lineups.home):
        assert all(sl.name is None for sl in lu.slots)
        assert len(lu.slots) == 11
        assert lu.formation is None            # we don't claim a formation


def test_honest_gaps_present():
    p = _build()
    assert len(p.honest_gaps.items) >= 4
    labels = " ".join(g.label for g in p.honest_gaps.items)
    assert "Lineups" in labels and "Tactical" in labels


# -------------------------------------------------------- rendering ----------
def test_all_sections_render_without_error():
    p = _build()
    fns = [
        C.hero_html(p.hero),
        C.snapshot_html(p.snapshot, p.hero.away.short, p.hero.home.short),
        C.tactical_html(p.tactical),
        C.storylines_html(p.storylines),
        C.lineups_html(p.lineups),
        C.players_html(p.players),
        C.attacking_html(p.attacking),
        C.discipline_html(p.discipline),
        C.timeline_html(p.timeline),
        C.honest_gaps_html(p.honest_gaps),
    ]
    full = "".join(fns)
    assert full.count("<div") == full.count("</div>")   # balanced
    assert "Coming soon" in full                          # unavailable badges present
    assert "Live" in full                                 # snapshot/available badges present


def test_dark_team_color_is_lightened_for_contrast():
    # A black brand color must not render invisibly on the charcoal canvas.
    assert C._safe_accent("#000000") != "#000000"
    assert C._safe_accent(None) == "var(--brand)"


def test_final_state_hero_shows_score():
    p = _build(state="final", away_score=1, home_score=2)
    html = C.hero_html(p.hero)
    assert "mls-hero-score" in html and "Final" in html
