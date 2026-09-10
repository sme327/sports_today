"""Record and grade the hand-written NFL prop leans.

    python -m scripts.nfl_leans record    # every content/nfl/*.toml → ledger (idempotent)
    python -m scripts.nfl_leans grade     # grade due games from ESPN's box score
    python -m scripts.nfl_leans show      # the ledger, newest game first

Both halves also run inside the daily rebuild (services/update_pipeline), non-fatally.
"""

from __future__ import annotations

import argparse
import sys

from services import nfl_leans


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("record", "grade", "show"))
    args = parser.parse_args(argv)
    if args.command == "record":
        for game_id, n in nfl_leans.record_all().items():
            print(f"{game_id}: {n} leans recorded")
        return 0
    if args.command == "grade":
        out = nfl_leans.grade_due()
        if not out:
            print("Nothing due.")
        for game_id, tally in out.items():
            print(f"{game_id}: {tally}")
        return 0
    rows = nfl_leans.load()
    for r in rows:
        actual = "" if r["actual"] is None else f" · actual {r['actual']:g}"
        print(f"{r['kickoff']} {r['game_id']} #{r['rank']:<2} {r['player']:<22} "
              f"{r['direction']} {r['line']:g} {r['stat']:<14} {r['confidence']:<8} "
              f"{r['result'] or 'pending'}{actual}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
