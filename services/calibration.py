"""What each market has actually converted, from the graded ledger.

An Opportunity Score is only comparable *within* a market. Measured on the same
50-69 band: total bases has converted 21.4% and SP hits allowed 60.0% — a 39-point
spread for an identical number. A reader comparing two props on one game page has no
way to know that.

This does **not** reorder anything. The served slate feed is 91% batter-hit and the
weak markets never reach it (zero total-bases props in the served top-15 across every
graded slate), so a cross-market sort would change nothing anyone sees. Where the
mixing genuinely happens is a single game's prop list, and there the honest fix is to
say what the market's record is rather than silently re-rank it.

Deliberately an **observed** rate with its sample size, never a predicted one: R4 rules
out "expected hit rate" wording, and this is history, not a forecast.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.config import DB_PATH

# Below this the market's record is too thin to hold against a reader's judgement.
MIN_GRADED = 100
# Rates at or below this are worth warning about; a market converting near or above
# the overall population rate needs no comment, and saying so on every prop would
# teach the reader to skip the line.
POOR_RATE = 0.35


@dataclass(frozen=True)
class MarketRecord:
    market_key: str
    hits: int
    misses: int

    @property
    def graded(self) -> int:
        return self.hits + self.misses

    @property
    def rate(self) -> float | None:
        return self.hits / self.graded if self.graded else None

    @property
    def usable(self) -> bool:
        return self.graded >= MIN_GRADED

    @property
    def is_poor(self) -> bool:
        return bool(self.usable and self.rate is not None and self.rate <= POOR_RATE)

    @property
    def note(self) -> str:
        """Factual and sample-sized — the reader draws the conclusion."""
        return (f"This market has converted {self.rate:.0%} of "
                f"{self.graded:,} graded picks")


def market_records(db_path: Path = DB_PATH) -> dict[str, MarketRecord]:
    """Every market's graded record. Empty on a missing DB — callers then say
    nothing, rather than implying a market is untested when it is only unreadable."""
    if not Path(db_path).exists():
        return {}
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """SELECT market_key,
                          SUM(result = 'hit'), SUM(result = 'miss')
                   FROM opportunity_snapshots
                   WHERE result IN ('hit','miss')
                     AND market_key IS NOT NULL AND market_key != ''
                   GROUP BY market_key""").fetchall()
    except Exception:
        return {}
    return {str(k): MarketRecord(str(k), int(h or 0), int(m or 0)) for k, h, m in rows}


def poor_market_note(market_key: str | None,
                     records: dict[str, MarketRecord] | None = None) -> str | None:
    """A caveat for a market with a bad track record, or None.

    Only fires for markets with a real sample and a genuinely poor record, so the
    line means something when it appears.
    """
    if not market_key:
        return None
    rec = (records if records is not None else market_records()).get(market_key)
    return rec.note if rec and rec.is_poor else None


def annotate(opportunities, records: dict[str, MarketRecord] | None = None):
    """Append the market caveat to each opportunity that warrants one.

    Mutates in place and returns the list, so callers can wrap a builder without
    restructuring. Opportunities in healthy markets are untouched.
    """
    records = records if records is not None else market_records()
    for opp in opportunities:
        note = poor_market_note(getattr(opp, "market_key", None), records)
        if note and note not in opp.negative_evidence:
            opp.negative_evidence.append(note)
    return opportunities
