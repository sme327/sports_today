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
            # The market's pregame view, recovered from what the daily run cached before
            # kickoff — ESPN has already dropped the odds from these games. Recorded
            # beside the result for measurement only; nothing scores from it, and
            # `interest` below never sees it.
            lines = go.pregame_lines(slate.isoformat(), adapter.league)
            for original, rewound in zip(finished, pre):
                detail = interest(rewound, norms.get(adapter.league))
                line = lines.get(str(original.game_id))
                # A zero interest score means editorial had nothing to say — two 0-0
                # teams in week one, most of an opening college slate. That used to end
                # the matter, because this table only calibrated interest. It now also
                # holds the market record, and a game with a line is worth keeping even
                # when we had no read on it: those are exactly the games the totals
                # question is about.
                if detail.score == 0 and not line:
                    continue
                row = go.outcome_for(original, detail.score, [s.kind for s in detail.signals],
                                     line=line)
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
        tr = go.totals_record(rows, lg)
        if tr["n"]:
            rate = f"{tr['over_rate']}% over" if tr["over_rate"] is not None else "no decided games"
            print(f"  {lg:6s} totals: n={tr['n']:3d}  {tr['over']}-{tr['under']}-{tr['push']} "
                  f"({rate}), mean result minus line {tr['mean_error']:+}")
        c = go.calibration(rows, lg)
        if c:
            h, l = c["high"], c["low"]
            print(f"  {lg:6s} n={c['n']:3d}  interest>=60: margin {h['mean_margin']} "
                  f"close {h['close_rate']} (n={h['n']})   <45: margin {l['mean_margin']} "
                  f"close {l['close_rate']} (n={l['n']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
