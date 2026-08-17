# Prediction evaluation contract

> **Purpose** — Define which predictions are public, how they are graded, and how
> model improvements earn promotion without hindsight or score inflation.

## Public cohorts

- **All qualifying** — every published prediction with Opportunity Score >= 70.
  These appear in matchup views and form the primary evaluation population.
- **Featured** — the highest-ranked eight qualifying predictions for a slate, also
  shown on Today. Their stored rank measures whether curation adds value.
- **Other qualifying** — qualifying predictions outside the featured eight. Comparing
  this cohort with Featured tests ranking separately from the underlying models.
- **Research only** — valid outputs below 70. These may be retained privately to study
  the cutoff and score shape, but never enter public performance claims.

Future snapshots store `featured` and `featured_rank`. Historical featured membership
is reconstructed only from immutable pregame snapshot scores, never outcomes.

## Reporting rules

Every result identifies its cohort, filters, period, and model version when relevant.
Prediction count and independent slate count appear together. Voids and pending rows do
not enter hit rate, but their counts and reasons remain visible.

The Performance page's **Market pulse** combines active markets in one matrix across the
latest graded slates. Each cell is judged against that market's own selected-period
average, never a universal hit-rate target; the period summary and recent-versus-prior
three-slate direction remain visible at the row edge. Cells under five decisions are
faded so volatility does not masquerade as evidence.

Core measurements are record, hit rate, coverage, void rate, predictions per slate,
score-band reliability, Featured precision at 1/3/5/8, results by market/threshold/
direction/version, and—once enough slates exist—uncertainty clustered by slate or game.

Opportunity Score is a ranking signal, not a probability. Raw scores from different
markets should not be treated as directly comparable; Featured selection should move
toward market-specific percentiles or properly calibrated probabilities.

## Model-development guardrails

- Preserve pregame inputs and the official daily snapshot. Never reconstruct a missing
  public prediction after results exist.
- Freeze candidate versions before forward evaluation. Keep training, model selection,
  and forward-test periods distinct.
- Compare candidates with the prior production version, a simple recent-form rule, and
  the market/base result rate. Higher hit rate caused only by lower coverage is not
  automatically an improvement.
- Evaluate correlated selections by slate/game/player; rows are not fully independent.
- Add probable starter, lineup, park/weather, pitch expectation, opponent pace/defense,
  availability, rest, or travel only through leakage-safe ablation tests.

## Current market posture

- Batter hits: primary MLB development market.
- Starting-pitcher strikeouts: promising but still small-sample.
- Starting-pitcher hits allowed: experimental pending more forward results.
- Batter strikeouts: retire or redesign; preserve its history.
- WNBA v3: evaluate separately from older versions once it has forward results.
- Total bases and walks: retired from the public interface; retain history.

## Operational quality gates

Before publishing, validate source freshness, schedule completeness, expected row
counts, snapshot presence, Featured ranks, grading completeness, static rendering, and
all internal links. Missing snapshots remain visibly missing rather than backfilled.
