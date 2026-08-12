# Method — how we decide whether something is real

> **Purpose** — The tests that decide whether a signal, a scorer change, or a "finding"
> is worth shipping. Every rule here changed a real conclusion in this project; each one
> cites the case that earned it.
> **Audience** — Engineers, product, and AI assistants proposing any change to scoring,
> editorial, or the models.
> **Update when** — A test proves itself, or fails to.
> **Related** — [Decision Log](DECISION_LOG.md) · [Historical Data](HISTORICAL_DATA.md) · [Testing](TESTING.md)

Most ideas that feel obviously right turn out to be noise, an artifact, or something the
world already knows. This file is the short list of checks that separate the three. Run
them **before** building, not after — every negative result below cost minutes and saved
days.

---

## 1. Measure lift over a base rate, never a raw rate

**A 40% hit rate on a bar that lands 15% of the time is excellent. A 56% hit rate on a bar
that lands 54% of the time is worthless.** Always ask "56% *of what?*".

This one measurement choice was distorting three separate decisions in the SP scorers at
once. Judged by raw conversion, `sp_hits` unders looked respectable at 0.561; judged
against the base rate for the thresholds they picked, they were **−0.011** — no
information at all. Meanwhile `sp_k` overs looked bad at 0.395 and were the app's best
signal at **+0.170**, because a 40% hit on a bar that lands 22% of the time is a large
edge. A refit (`sp-v2`) had penalised them for it.

**Applies to:** any hit-rate comparison, any threshold choice, any "which market is
working" question. See `sp-v3` and the 2026-08-10 entries.

## 2. Split-half persistence: is it a trait, or a run of luck?

Split the population in half — by time, by odd/even occurrences — compute the effect in
each half, and correlate. A real, persistent property correlates. A hot streak does not.

Calibrate against something known to be real. Overall batter hit rate gives **r = +0.576**
on this data. Against that yardstick:

| candidate | split-half r | verdict |
|---|---|---|
| overall hit rate *(control)* | **+0.576** | real |
| MLB park factor | +0.413 | real (but see rule 4) |
| CBB conference over/under tendency | +0.252 | suggestive, n=29 — see rule 5 |
| batter home/road split | +0.127 | weak |
| **platoon splits** | **+0.077** | **not a trait** |
| **umpire over/under tendency** | **+0.057** | **not a trait** |
| batter × park | +0.047 | noise |

Platoon splits are the cautionary tale: with five seasons the effect finally became
*measurable* (5.5% of batters exceeded a .040 split), and it still did not **persist**.
Measurable is not real.

## 3. A huge effect in an efficient market is a leak

NBA fast-pace games went over **61.4% (+9.7 SE)**. That used `pace` computed *from the
game itself* — more possessions, more points, more overs. Circular. Re-run with each
team's **prior** pace: +1.3 SE. Nothing.

**Any result large enough to be exciting should trigger a leakage check first.** Ask: could
this feature only be known *after* the outcome? The `as_of` rule exists for exactly this,
and analysis scripts do not get it for free.

## 4. Validate in the population you will actually serve

An effect that is real in the historical data may not survive into the props you show.

MLB park factor is genuinely persistent (r = +0.413, a 12-point range on P(1+ hit)). Across
2,714 graded props, `corr(park factor, win)` was **+0.025** and the terciles were not
monotonic. A full-strength effect predicted a ~7.3-point tercile spread; observed was 1.2
against an SE of ~1.6. **Real in the history, absent in the product.** Not built.

## 5. Expect outliers: the largest of *k* tries is about `√(2 ln k)` SE

Before looking at the extremes of a scan, compute what chance alone produces. Across 71
umpires that is ~2.9 SE; across 29 conferences ~2.6.

This turned three "findings" into noise on sight. One umpire's games went under 69%
(−3.2 SE) — barely past chance across 71, and his seasons ran 0.571 / 0.286 / 0.250 /
0.375. One CBB conference hit 58.8% unders — and it was 53.0% then 64.9% by season, i.e.
one year.

**Report the number of splits tested alongside the best one.** A single result quoted
without its search space is not evidence.

## 6. Ask "does anyone not already know?", not just "is this true?"

The sharpest correction this project has made. The NBA back-to-back fatigue signal was
logged as the first to survive out-of-sample validation: underdogs at home against a
favourite on a B2B won **42.9%** against a 30.1% base, replicating across halves.

Then measured against the **closing line** instead of against records: B2B favourites cover
**49.3%**. Every cut within ±0.7pp of 50%. The effect is real, replicating, and **entirely
priced**. Descriptive, not predictive.

**Where a market exists, it is the benchmark.** Records-based signals answer "is this
true?" — the line answers "is this news?". Odds stay **offline** for exactly this: a
validation gate, never an input (see rule 8).

## 7. Ship only if the spread widens *and* the top lifts

The gate for any scoring change, on **held-out** data — fit on one period, test on
another. `batter-hit-v5` passed:

| | shrink 0.70 | shrink 0.25 |
|---|---|---|
| test correlation | +0.1127 | **+0.1314** |
| served conversion | 0.6304 | **0.6417** |
| top-20% conversion | 0.6419 | **0.6556** |
| spread over bottom 20% | +0.1613 | **+0.1879** |

Prefer a **monotonic trend** over a picked optimum — a best value that its neighbours do
not support is usually a fitted one. And re-tune coupled constants **together**: changing
`_LEAGUE_HIT_RATE` alone made things look worse only because the score scale had been
tuned around the old value.

## 8. Some rules are product decisions, and evidence does not override them

- **"Opportunity Score", never probability.** Do not convert scores to percentages, even
  when a backtest makes it tempting. Empirical base rates are the honest alternative.
- **Odds are offline-only.** They benchmark and validate; they never feed a surface. Using
  the closing line inside Game Interest would make the score accurate and make it a
  repackaging of the market rather than our own read.
- **Never join on names.** Join on ids, or on a normalised dimension plus a date.
- **Missing is missing.** `None` beats a derived guess — the vendor prices only the
  favourite in some MLB seasons, so the underdog's moneyline stays empty.

## 9. Validate a new data source against something it has never seen

A collector that parses without erroring is not a collector that is correct. Check it
against an independent source where one exists — the ESPN box-score collector was built
NBA-first *because* six vendor seasons could contradict it — and against the sport's own
real-world rates where none does. NHL had no second source, so it was checked against
hockey: 26.7 shots on goal per team per game, 3.0 goals, 19.7 hits. A stat sitting at
exactly 0.0 is the loudest signal available, and it is invisible if you only read the
schema.

**And when a debug value looks odd, check it.** A `None` in a throwaway print was dismissed
as a formatting artifact; it was two stat columns silently unmapped.

## 10. Write the negative result down

Roughly two thirds of the investigations in the [Decision Log](DECISION_LOG.md) are
negatives, and they are the most valuable entries in it: platoon splits, prior-season
priors, park factor, `richer_game_outcomes` for MLB, totals in three sports, porting v5 to
WNBA. Each one **closed** a line of work that looked obviously worth doing.

Record what was tested, the number, and why it failed. A negative without its evidence
gets re-run in three months.

---

## The five-minute version

1. Lift over base rate, not raw rate.
2. Split-half it — does the trait persist?
3. Too good? Check for leakage.
4. Real in history ≠ real in the served population.
5. `√(2 ln k)` before admiring an outlier.
6. Would the market already know?
7. Widen the spread *and* lift the top, out of sample.
8. Validate a new source against something it has never seen.
9. Write the negative down.
