"""Hand-authored game notes: parsing, the spotlight filter, and the rendered sections."""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from components.nfl_game import page_html
from services.nfl_game_notes import load_notes, parse_notes
from services.nfl_game_page import build_nfl_pregame_page

_NOTE = b"""
game_id = "401"
away = "A"
home = "B"
kickoff = "2025-09-03"
authored = "2025-09-03"
report_date = "2025-09-02"

[[availability]]
team = "A"
player = "Rex Runner"
position = "RB"
status = "Out"
detail = "ankle"
impact = "The passing-down back is gone; Bob Backup takes the carries."

[[availability]]
team = "A"
player = "Sam Snapper"
position = "LS"
status = "Questionable"

[[availability]]
team = "B"
player = "Sal Safety"
position = "S"
status = "Questionable"

[[changes]]
team = "A"
direction = "in"
text = "WR Big Name, by trade"

[read]
game_script = "Slow, then slower."

[[falsifiers]]
condition = "A scores early"
consequence = "The slow-game thesis is wrong."

[[props]]
team = "B"
player = "Sal Safety"
stat = "receiving_yds"
line = 10.5
direction = "pass"
why = "No edge."

[[props]]
team = "A"
player = "Bob Backup"
stat = "rushing_att"
line = 9.5
direction = "over"
confidence = "moderate"
why = "The carries are his."

[shape]
headline = "A slow one."
observations = [ { lead = "Both defences are good.", text = "Neither scored much." } ]
alternative = "Or a shootout."

[[preline]]
team = "A"
player = "Quincy Quarterback"
market = "Passing yards"
direction = "under"
why = "Written before the line."

[[leans]]
team = "A"
player = "Quincy Quarterback"
stat = "passing_yds"
line = 240.5
direction = "under"
confidence = "high"
why = "Tough pass defence."

[[overs]]
team = "B"
player = "Sal Safety"
stat = "receptions"
line = 1.5
direction = "over"
confidence = "low"
why = "A safety who catches passes, apparently."

[[volume]]
team = "A"
player = "Bob Backup"
stat = "receptions"
line = 2.5
direction = "under"
confidence = "low"
why = "Volume board entry."

[[sources]]
title = "The report"
url = "https://example.com/report"
"""


def test_parse_reads_every_section():
    n = parse_notes(_NOTE)
    assert n.game_id == "401" and n.report_date == "2025-09-02"
    assert n.sidelined() == {"Rex Runner"}          # Questionable is not sidelined
    assert n.sidelined("B") == frozenset()
    assert n.changes[0].direction == "in"
    assert n.shape_headline.startswith("A slow") and n.shape == ()
    assert n.shape_observations == (("Both defences are good.", "Neither scored much."),)
    assert n.leans[0].direction == "under" and n.sources[0].url.startswith("https://")
    assert n.leans[0].market == "Under 240.5 passing yards" and n.leans[0].section == "leans"
    assert n.in_section("overs")[0].market == "Over 1.5 receptions"
    assert n.in_section("volume")[0].section == "volume" and len(n.leans) == 5
    assert n.preline[0].direction == "under" and n.preline[0].market == "Passing yards"
    assert n.game_script == "Slow, then slower."
    assert n.falsifiers[0].condition == "A scores early"
    board = n.in_section("props")
    assert [l.direction for l in board] == ["pass", "over"]
    assert board[0].market == "10.5 receiving yards" and board[0].confidence == ""
    assert len(n.called) == len(n.leans) - 1
    assert n.availability[0].impact.startswith("The passing-down back")
    assert len(n.fingerprint) == 10


@pytest.mark.parametrize("bad, message", [
    (b'status = "Out"', b'status = "Hurt"'),
    (b'direction = "under"\nconfidence', b'direction = "fade"\nconfidence'),
    (b'direction = "in"', b'direction = "added"'),
    (b'stat = "passing_yds"', b'stat = "passing_yardage"'),
    (b'confidence = "high"', b'confidence = "lock"'),
    (b'line = 240.5', b'line = "two forty"'),
    # the overs section holds overs only
    (b'line = 1.5\ndirection = "over"', b'line = 1.5\ndirection = "under"'),
    # the volume board holds volume stats only
    (b'stat = "receptions"\nline = 2.5', b'stat = "receiving_yds"\nline = 2.5'),
    # a pass is only a board direction; an over on the board still needs a confidence
    (b'direction = "under"\nconfidence = "high"', b'direction = "pass"\nconfidence = "high"'),
    (b'direction = "over"\nconfidence = "moderate"\nwhy = "The carries', b'direction = "over"\nwhy = "The carries'),
])
def test_a_typo_fails_loudly(bad, message):
    with pytest.raises(ValueError):
        parse_notes(_NOTE.replace(bad, message))


def test_load_is_none_without_a_file_and_checks_the_id(tmp_path):
    assert load_notes("401", notes_dir=tmp_path) is None
    assert load_notes(None, notes_dir=tmp_path) is None
    (tmp_path / "402.toml").write_bytes(_NOTE)
    with pytest.raises(ValueError):
        load_notes("402", notes_dir=tmp_path)       # file says 401
    (tmp_path / "401.toml").write_bytes(_NOTE)
    assert load_notes("401", notes_dir=tmp_path).game_id == "401"


# --- the spotlight filter: an Out or Departed player is not spotlighted -----------

def _t(gid, wk, team, opp, venue, pts):
    return {"game_id": gid, "game_date": f"2025-09-{wk:02d}", "week": wk, "season": 2025,
            "season_type": "regular", "team": team, "opponent": opp, "venue": venue,
            "final": pts, "yards_total_yards": 400, "passing_yds": 280, "rushing_yds": 120,
            "total_plays": 64, "passing_att": 32, "rushing_rush": 26, "passing_comp": 21,
            "turnovers_penalties_turnovers": 1, "third_downs_made": 6, "third_downs_att": 14,
            "first_downs": 21, "sacks_sacked": 2, "passing_int": 1}


def _p(gid, wk, team, pid, name, pos, **stats):
    row = {"game_id": gid, "game_date": f"2025-09-{wk:02d}", "week": wk, "season": 2025,
           "player_id": pid, "player": name, "position": pos, "team": team, "opponent": "B",
           "passing_att": 0, "passing_yds": 0, "rushing_att": 0, "rushing_yds": 0,
           "receiving_tar": 0, "receiving_rec": 0, "receiving_yds": 0}
    row.update(stats)
    return row


def _seed(tmp_path):
    db = tmp_path / "nfl.db"
    tg, pg = [], []
    for wk in range(1, 6):
        gid = f"g{wk}"
        tg += [_t(gid, wk, "A", "B", "Road", 24), _t(gid, wk, "B", "A", "Home", 20)]
        pg += [_p(gid, wk, "A", "rex", "Rex Runner", "RB", rushing_att=18, rushing_yds=80),
               _p(gid, wk, "A", "bob", "Bob Backup", "RB", rushing_att=9, rushing_yds=40),
               _p(gid, wk, "A", "q", "Quincy Quarterback", "QB", passing_att=30, passing_yds=250)]
    with sqlite3.connect(db) as conn:
        pd.DataFrame(tg).to_sql("nfl_team_games", conn, index=False)
        pd.DataFrame(pg).to_sql("nfl_player_games", conn, index=False)
    return db


def test_sidelined_players_are_not_spotlighted(tmp_path):
    db = _seed(tmp_path)
    (tmp_path / "401.toml").write_bytes(_NOTE)
    plain = build_nfl_pregame_page("A", "B", "2025-09-10", slate_season=2026, db_path=db)
    assert [s.player for s in plain.away_spotlights if s.position == "RB"] == ["Rex Runner"]
    assert plain.notes is None

    page = build_nfl_pregame_page("A", "B", "2025-09-10", slate_season=2026, db_path=db,
                                  event_id="401", notes_dir=tmp_path)
    assert page.notes is not None and page.notes.game_id == "401"
    names = [s.player for s in page.away_spotlights]
    assert "Rex Runner" not in names
    assert "Bob Backup" in names                     # the next man up is picked instead
    assert "Quincy Quarterback" in names             # a lean is not a removal


def test_rendered_sections_and_disclaimer(tmp_path):
    db = _seed(tmp_path)
    (tmp_path / "401.toml").write_bytes(_NOTE)
    page = build_nfl_pregame_page("A", "B", "2025-09-10", slate_season=2026, db_path=db,
                                  event_id="401", notes_dir=tmp_path)
    html = page_html(page)
    for text in ("Availability", "Since last season", "Tonight&#x27;s matchup", "Before seeing the lines",
                 "Also on the report", "Sam Snapper", "The passing-down back is gone", "nfl-dir pass",
                 "Prop leans", "Volume board", "Looking for overs", "Under 240.5 passing yards",
                 "Over 1.5 receptions", "Written before the line.", "Both defences are good.",
                 "Neither scored much.", "Rex Runner", "Sal Safety", "Big Name", "A slow one.",
                 "Or a shootout.", "Quincy Quarterback", "Tough pass defence.",
                 "https://example.com/report", "2025-09-02", "not graded", "/leans/",
                 "Methodology"):
        assert text in html, text
    assert 'nfl-status out' in html and 'nfl-status q' in html
    assert 'nfl-dir under' in html and 'nfl-dir pre' in html and 'nfl-conf high' in html
    # The page order: game → thesis → personnel → strategy → numbers → players → props →
    # supporting detail → methodology. Every section is still there, in that order.
    order = ["nfl-hero", "Tonight&#x27;s matchup", "Availability", "The read",
             "Expected game script", "Slow, then slower.", "Matchup at a glance",
             "Player spotlights", "Prop board", "1 call out of 2 lines evaluated",
             "Prop leans", "Volume board", "Looking for overs", "Recent form",
             "Since last season", "What would change the read", "If A scores early",
             "Before seeing the lines", "Methodology", "Sources:"]
    positions = [html.index(t) for t in order]
    assert positions == sorted(positions), list(zip(order, positions))
    # Out ranks above Questionable inside a team's availability column
    assert html.index("Rex Runner") < html.index("Sal Safety")
    # The pre-line read is an appendix: a details element, closed by default.
    assert '<details class="nfl-sec nfl-sec--support nfl-sec--appendix">' in html
    assert "<details open" not in html
    # The three prop sections carry distinct treatments.
    for cls in ("nfl-sec--leans", "nfl-sec--volume", "nfl-sec--overs"):
        assert cls in html, cls
    assert "hand-entered" in html and "not modeled" in html
    # Without a note the page still says injuries are not modeled, and shows no notes.
    plain = page_html(build_nfl_pregame_page("A", "B", "2025-09-10", slate_season=2026, db_path=db))
    assert "Prop leans" not in plain and "injuries" in plain
