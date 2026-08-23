from __future__ import annotations

from datetime import date, timedelta

from scripts import signal_discovery as S


def _rows(days=30, per_day=3):
    rows = []
    start = date(2026, 6, 1)
    for day in range(days):
        for player in range(per_day):
            rows.append({
                "snapshot_date": (start + timedelta(days=day)).isoformat(),
                "league": "WNBA", "market": "8+ Rebounds", "market_key": "wnba_rebounds",
                "player_id": f"p{player}", "team_name": "A", "opponent": "X",
                "direction": "over", "threshold": 8, "opportunity_score": 85,
                "featured": player == 0, "result": "hit" if player < 2 else "miss",
                "scoring_engine_version": S.MODEL_VERSIONS.get("wnba_rebounds"),
            })
    return rows


def test_report_promotes_only_a_strength_that_survives_the_holdout(monkeypatch, tmp_path):
    rows = _rows()
    monkeypatch.setattr(S.grading, "load_graded_range", lambda *a, **k: rows)
    monkeypatch.setattr(S.base_rates, "row_base_rate", lambda row, db_path=None: 0.45)
    report = S.analyze(db_path=tmp_path / "x.db", as_of=date(2026, 8, 1))
    strengths = [c for c in report["candidates"] if c["status"] == "confirmed"]
    assert strengths
    assert all(c["validation"]["lift"] > 0 for c in strengths)
    assert "Discovery/validation split" in S.markdown(report)


def test_market_first_scan_deduplicates_single_value_conditions():
    groups = S._candidate_groups(_rows(days=1, per_day=2))
    signatures = []
    for subset in groups.values():
        signatures.append(tuple(sorted((r["snapshot_date"], r["player_id"]) for r in subset)))
    assert len(signatures) == len(set(signatures))


def test_monthly_report_skips_when_the_existing_report_is_fresh(tmp_path):
    md, js = tmp_path / "report.md", tmp_path / "report.json"
    md.write_text("current")
    assert S.write_report(force=False, db_path=tmp_path / "x.db",
                          output_md=md, output_json=js) is None
