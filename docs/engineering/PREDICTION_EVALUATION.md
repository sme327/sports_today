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
average, never a universal hit-rate target. Since 2026-09-09 the recent-versus-prior
three-slate direction is its own **Trend** column rather than a note at the row edge —
"is this market improving or deteriorating" is the question a row of eight percentages
cannot answer at a glance — and it stays gated on both windows carrying ten decisions.
Cells under five decisions are faded so volatility does not masquerade as evidence, and
cells now also fade with **age**: the grid is texture behind the trend column, and eight
equally-saturated columns made ordinary variance look like a row of findings.

Core measurements are record, hit rate, coverage, void rate, predictions per slate,
score-band reliability, Featured precision at 1/3/5/8, results by market/threshold/
direction/version, and—once enough slates exist—uncertainty clustered by slate or game.

Opportunity Score is a ranking signal, not a probability. Raw scores from different
markets should not be treated as directly comparable; Featured selection should move
toward market-specific percentiles or properly calibrated probabilities.

**Any conclusion the surface states is computed from lift over base and gated on sample,
never from a raw rate** (2026-09-09). This binds the generated text and the market
classifications, not just the tables: a hit rate is a property of the props served as much
as of the picking, and "63% accurate" against a 52% base is the most flattering true
sentence available. The judgements live in `services/model_trust.py` so each is testable
as a claim rather than as markup, and two properties are guarded there — sample size gates
the *ordering* of a ranking and not merely its labelling, and a conclusion is allowed to be
negative or absent (a version that lost ground reads as having lost ground; a category with
nothing to say is dropped, never padded). See [Method §1a](METHOD.md).

## Recurring signal discovery

The normal update attempts `scripts.signal_discovery` every day but writes a new local
report only every 28 days (`logs/signal_discovery_latest.md` plus machine-readable JSON).
Run `python -m scripts.signal_discovery --force` for an interim report.

The scan covers every decided 70+ prediction for active market families, while keeping
each scoring-engine version separate. Candidate slices are deliberately bounded to one
condition within a market/version: direction, threshold, score band, Featured status,
team, or opponent. It does not mine arbitrary multi-factor conjunctions.

A candidate needs at least 30 decisions across five slates to enter the report. Its own
slates are split chronologically 70/30 into discovery and validation; lift uses each
row's exact natural base rate; uncertainty is clustered by slate; discovery p-values are
Benjamini–Hochberg corrected. “Confirmed” additionally requires 60 decisions, 15 slates,
a positive clustered 95% lower bound, q≤.10, and positive later holdout lift. Earlier
positive results remain explicitly a **Promising watchlist**, never a production rule.

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

**The Performance page's trust board is the living version of this list** — it tiers every
market on lift over base, sample and recent trend on whatever period is selected, so it
cannot drift the way a hand-written list does. What follows is the standing posture, with a
dated snapshot of what the board actually said.

- Batter hits: primary MLB development market. Real but modest edge on by far the largest
  sample; the market whose raw hit rate is most likely to be mistaken for skill.
- Starting-pitcher strikeouts: the strongest MLB market on a large sample.
- Starting-pitcher hits allowed: flat rather than failing — measured −4.1 ±6.2 in 2026-08,
  not significant, so not a retirement candidate. Keep measuring.
- Batter strikeouts: **no longer "retire or redesign"** — `batter-k-v2` (2026-08-20) fixed
  it by adding the opposing starter. It is now capped by *serving*, not by skill: the
  reachable-bar filter leaves it clearing the floor rarely, so it stays small-sample.
- WNBA: evaluate each version against the one it replaced, not against pooled history.
- Total bases and walks: retired from the public interface; retain history.

*Snapshot, 30 days to 2026-09-09 (all qualifying).* Strong signal — Rebounds +33.4 (n=157),
Assists +29.9 (n=128), Points +25.1 (n=194), SP Strikeouts +13.6 (n=479). Promising —
Batter Hits +5.7 (n=1,403). Watch — SP Hits Allowed +1.5 (n=340). Too early to say — Batter
Ks +41.8 on n=22, which is the number this contract exists to stop anyone acting on.
Versions: 3 of 7 current engines ahead of the ones they replaced; `batter-hit-v6` sits 2.6
points *behind* `batter-hit-v5`.

## Operational quality gates

Before publishing, validate source freshness, schedule completeness, expected row
counts, snapshot presence, Featured ranks, grading completeness, static rendering, and
all internal links. Missing snapshots remain visibly missing rather than backfilled.
