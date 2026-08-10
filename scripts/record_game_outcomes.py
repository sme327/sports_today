"""Record how interesting each finished game actually turned out to be.

    python -m scripts.record_game_outcomes              # yesterday
    python -m scripts.record_game_outcomes --days 21    # backfill a window

Scores each game on what was knowable at first pitch — ESPN's completed-game record
includes that game, so it is rewound first (see services.game_outcomes.pregame_record).
Without that the winner always looks stronger than they were, and the calibration this
feeds would flatter itself.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import leagues  # noqa: F401  (register adapters)
from leagues.base import iter_adapters
from services import game_outcomes as go
from services.editorial import interest, league_norms


def run(days: int = 1, verbose: bool = True) -> int:
    written = 0
    for back in range(1, days + 1):
        slate = date.today() - timedelta(days=back)
        rows = []
        for adapter in iter_adapters():
            try:
                games = adapter.fetch_schedule(slate)
            except Exception:
                continue
            finished = [g for g in games if g.state == "final"]
            if not finished:
                continue
            pre = [go.as_pregame(g) for g in finished]      # undo the result leak
            norms = league_norms(pre)
            for original, rewound in zip(finished, pre):
                detail = interest(rewound, norms.get(adapter.league))
                if detail.score == 0:
                    continue                                # nothing known; nothing to grade
                row = go.outcome_for(original, detail.score, [s.kind for s in detail.signals])
                if row:
                    rows.append(row)
        n = go.record(rows)
        written += n
        if verbose and n:
            print(f"  {slate}: recorded {n} finished games", flush=True)
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=1, help="how many days back to cover")
    args = ap.parse_args()
    total = run(args.days)
    print(f"recorded {total} game outcomes")
    rows = go.load()
    for lg in sorted({r["league"] for r in rows}):
        c = go.calibration(rows, lg)
        if c:
            h, l = c["high"], c["low"]
            print(f"  {lg:6s} n={c['n']:3d}  interest>=60: margin {h['mean_margin']} "
                  f"close {h['close_rate']} (n={h['n']})   <45: margin {l['mean_margin']} "
                  f"close {l['close_rate']} (n={l['n']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
