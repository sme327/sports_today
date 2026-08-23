"""Periodic, leakage-safe search for prediction segments that outperform their base.

The report is deliberately conservative. Candidate conditions are selected on the
earlier 70% of graded slates, multiple-testing adjusted there, and then checked on the
later 30%. Uncertainty is clustered by slate because dozens of props from one day are
not dozens of independent experiments.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from domain import markets
from services import base_rates, grading
from services.snapshots import MODEL_VERSIONS
from src.config import DB_PATH, LOG_DIR

REPORT_MD = LOG_DIR / "signal_discovery_latest.md"
REPORT_JSON = LOG_DIR / "signal_discovery_latest.json"
CADENCE_DAYS = 28
MIN_N = 30
MIN_SLATES = 5


def _market_key(row: dict) -> str:
    key = row.get("market_key")
    return str(key or markets.resolve(row.get("league"), row.get("market"))[0] or "unknown")


def _band(score) -> str:
    value = int(score or 0)
    return "90+" if value >= 90 else "80–89" if value >= 80 else "70–79"


def _candidate_groups(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Market-first one-condition slices; never search arbitrary conjunctions."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        version = str(row.get("scoring_engine_version") or "legacy")
        market = f"{row.get('league')} · {_market_key(row)} · {version}"
        groups[(market, "All qualifying")].append(row)
        conditions = {
            "Direction": str(row.get("direction") or "unknown").title(),
            "Threshold": f"{float(row['threshold']):g}" if row.get("threshold") is not None else "unknown",
            "Score band": _band(row.get("opportunity_score")),
            "Cohort": "Featured" if row.get("featured") else "Other qualifying",
            "Team": str(row.get("team_name") or "unknown"),
            "Opponent": str(row.get("opponent") or "unknown"),
        }
        for dimension, value in conditions.items():
            if value != "unknown":
                groups[(market, f"{dimension}: {value}")].append(row)
    # Identical row sets arise when a market has only one direction/threshold. Keep the
    # least-specific label so the report never presents the same finding repeatedly.
    unique: dict[tuple, tuple[tuple[str, str], list[dict]]] = {}
    for key, subset in groups.items():
        signature = tuple(sorted((r.get("snapshot_date"), r.get("league"),
                                  r.get("player_id"), r.get("market")) for r in subset))
        if signature not in unique:
            unique[signature] = (key, subset)
    return dict(unique.values())


def _stats(rows: list[dict], db_path: Path) -> dict:
    decided = [r for r in rows if r.get("result") in ("hit", "miss")]
    n = len(decided)
    slates = len({r.get("snapshot_date") for r in decided})
    if not n:
        return {"n": 0, "slates": 0, "rate": None, "base": None, "lift": None,
                "se": None, "ci_low": None, "ci_high": None, "p": 1.0}
    residuals = []
    by_slate: dict[str, list[float]] = defaultdict(list)
    for row in decided:
        base = base_rates.row_base_rate(row, db_path=db_path)
        if base is None:
            continue
        residual = (1.0 if row.get("result") == "hit" else 0.0) - base
        residuals.append(residual)
        by_slate[str(row.get("snapshot_date"))].append(residual)
    if not residuals:
        return {"n": n, "slates": slates, "rate": None, "base": None, "lift": None,
                "se": None, "ci_low": None, "ci_high": None, "p": 1.0}
    n_eff = len(residuals)
    lift = sum(residuals) / n_eff
    rate = sum(r.get("result") == "hit" for r in decided) / n
    base = rate - lift
    clusters = list(by_slate.values())
    if len(clusters) >= 2:
        sums = [sum(value - lift for value in values) for values in clusters]
        variance = (len(clusters) / (len(clusters) - 1)) * sum(v * v for v in sums) / (n_eff * n_eff)
        se = math.sqrt(max(variance, 0.0))
    else:
        se = None
    z = lift / se if se and se > 0 else 0.0
    # Zero clustered variance means every independent slate produced the same lift;
    # it is stronger evidence, not an undefined result to demote to p=1.
    p = (0.5 * math.erfc(z / math.sqrt(2)) if lift > 0 and se and se > 0
         else 0.0 if lift > 0 and se == 0 and len(clusters) >= 2 else 1.0)
    return {"n": n, "slates": slates, "rate": rate, "base": base, "lift": lift,
            "se": se, "ci_low": lift - 1.96 * se if se is not None else None,
            "ci_high": lift + 1.96 * se if se is not None else None, "p": p}


def _bh(items: list[dict]) -> None:
    ordered = sorted(enumerate(items), key=lambda pair: pair[1]["discovery"]["p"])
    m = len(ordered)
    running = 1.0
    for reverse_rank, (index, item) in enumerate(reversed(ordered), 1):
        rank = m - reverse_rank + 1
        running = min(running, item["discovery"]["p"] * m / rank)
        items[index]["q"] = min(1.0, running)


def analyze(*, db_path: Path = DB_PATH, as_of: date | None = None) -> dict:
    end = as_of or date.today()
    rows = grading.load_graded_range(date(2020, 1, 1), end, db_path=db_path)
    # Preserve historical evidence but never pool scoring engines. The version is part
    # of every candidate's market identity, so a formula change cannot manufacture a
    # trend. Retired market keys stay out of this recurring public-product scan.
    rows = [r for r in rows if (r.get("opportunity_score") or 0) >= grading.CURATION_FLOOR
            and r.get("result") in ("hit", "miss")
            and _market_key(r) in MODEL_VERSIONS]
    dates = sorted({str(r.get("snapshot_date")) for r in rows})
    split_at = max(1, math.ceil(len(dates) * 0.70)) if dates else 0
    discovery_dates, validation_dates = set(dates[:split_at]), set(dates[split_at:])
    candidates = []
    for (market, condition), subset in _candidate_groups(rows).items():
        # Split within this candidate's own lifetime. A global cutoff would put a new
        # model entirely in the holdout merely because an older model existed first.
        own_dates = sorted({str(r.get("snapshot_date")) for r in subset})
        own_split = max(1, math.ceil(len(own_dates) * 0.70))
        own_discovery = set(own_dates[:own_split])
        own_validation = set(own_dates[own_split:])
        overall = _stats(subset, db_path)
        discovery = _stats([r for r in subset if r.get("snapshot_date") in own_discovery], db_path)
        validation = _stats([r for r in subset if r.get("snapshot_date") in own_validation], db_path)
        if overall["n"] < MIN_N or overall["slates"] < MIN_SLATES:
            continue
        candidates.append({"market": market, "condition": condition, "overall": overall,
                           "discovery": discovery, "validation": validation, "q": 1.0})
    _bh(candidates)
    for item in candidates:
        d, v, o = item["discovery"], item["validation"], item["overall"]
        confirmed = (o["n"] >= 60 and o["slates"] >= 15 and d["n"] >= 30
                     and d["ci_low"] is not None and d["ci_low"] > 0
                     and item["q"] <= 0.10 and v["n"] >= 15
                     and v["slates"] >= 3 and (v["lift"] or 0) > 0)
        promising = (not confirmed and d["n"] >= 20 and d["slates"] >= 3
                     and v["slates"] >= 2 and item["q"] <= 0.20
                     and (d["lift"] or 0) > 0 and (v["lift"] or 0) > 0)
        item["status"] = "confirmed" if confirmed else "promising" if promising else "noise"
    candidates.sort(key=lambda x: ({"confirmed": 0, "promising": 1, "noise": 2}[x["status"]],
                                   -(x["overall"]["lift"] or -1), -x["overall"]["n"]))
    return {"generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": end.isoformat(), "decisions": len(rows), "slates": len(dates),
            "discovery_slates": len(discovery_dates), "validation_slates": len(validation_dates),
            "candidate_count": len(candidates), "candidates": candidates}


def _pct(value) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def markdown(report: dict) -> str:
    lines = ["# Sports Today — Signal Discovery Report", "",
             f"Generated {report['generated_at']} · results through {report['as_of']}", "",
             f"Population: {report['decisions']:,} decided qualifying predictions across "
             f"{report['slates']} slates. Discovery/validation split: "
             f"{report['discovery_slates']}/{report['validation_slates']} slates overall; "
             "each model segment is split within its own lifetime.", "",
             "Candidates are market-first, one-condition slices. Lift is measured against "
             "each row's exact natural base rate; uncertainty is clustered by slate; "
             "discovery p-values use Benjamini–Hochberg correction; confirmed findings "
             "must remain positive in the later holdout period.", ""]
    for status, title in (("confirmed", "Confirmed strengths"),
                          ("promising", "Promising watchlist")):
        found = [c for c in report["candidates"] if c["status"] == status]
        lines += [f"## {title}", ""]
        if not found:
            lines += ["None yet.", ""]
            continue
        lines += ["| Market | Condition | Record | Hit rate | Base | Lift | Holdout lift | q |",
                  "|---|---|---:|---:|---:|---:|---:|---:|"]
        for c in found[:20]:
            o, v = c["overall"], c["validation"]
            hits = round((o["rate"] or 0) * o["n"])
            lines.append(f"| {c['market']} | {c['condition']} | {hits}–{o['n']-hits} "
                         f"(n={o['n']}, {o['slates']} slates) | {_pct(o['rate'])} | "
                         f"{_pct(o['base'])} | {_pct(o['lift'])} | {_pct(v['lift'])} | "
                         f"{c['q']:.3f} |")
        lines.append("")
    lines += ["## Scan accounting", "",
              f"{report['candidate_count']} candidate segments cleared the basic "
              f"n≥{MIN_N} and ≥{MIN_SLATES}-slate screen. Segments not shown above are "
              "retained in the JSON output as noise/insufficient evidence, not promoted.", ""]
    return "\n".join(lines)


def write_report(*, force: bool = False, db_path: Path = DB_PATH,
                 output_md: Path = REPORT_MD, output_json: Path = REPORT_JSON) -> Path | None:
    if not force and output_md.exists():
        age = datetime.now() - datetime.fromtimestamp(output_md.stat().st_mtime)
        if age < timedelta(days=CADENCE_DAYS):
            return None
    report = analyze(db_path=db_path)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(markdown(report), encoding="utf-8")
    output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output_md


def main() -> int:
    parser = argparse.ArgumentParser(description="Find repeatable strengths in the graded ledger.")
    parser.add_argument("--force", action="store_true", help="Generate even if the monthly report is current.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()
    path = write_report(force=args.force, db_path=args.db)
    print(f"Signal report written: {path}" if path else "Signal report is current; skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
