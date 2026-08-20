# Decision Log

> **Purpose** — A living record of significant product and engineering decisions: what we decided, why, the tradeoffs, and what to revisit. Read this before proposing a change that reverses one of these.
> **Audience** — Engineers, product, design, and AI assistants.
> **Update when** — A significant decision is made or reversed. Append a new entry; don't rewrite history — supersede it.
> **Related** — [Architecture](ARCHITECTURE.md) · [Vision](../product/VISION.md) · [Design System](../design/DESIGN_SYSTEM.md) · [Docs index](../README.md)

Newest first. Each entry: **Decision · Reason · Tradeoffs · Future considerations.**

---

## 2026-08-20 — Judge a market on everything it predicted, not on what we served

**Decision.** Three changes to the Performance page, plus two infrastructure fixes that
had been hiding shipped work.

### Market coverage — the blind spot

Every table on the page read **served** predictions. A market whose scorer cannot reach
the curation floor is therefore invisible *by construction*, and indistinguishable from one
that does not work. `batter_k` carries the second-highest lift of any market and had been
served four times. It was found by accident with an ad-hoc script.

| market | all predictions | served (70+) | share |
|---|---|---|---|
| Assists | +18.0 (n=170) | +30.5 (n=79) | 46% |
| **Batter Ks** *starved* | **+16.9 (n=80)** | +28.2 (n=4) | **5%** |
| Rebounds | +10.7 (n=203) | +31.1 (n=75) | 37% |
| SP Strikeouts | +7.2 (n=300) | +10.2 (n=225) | 75% |
| Batter Hits | −3.4 (n=3,383) | +2.5 (n=1,020) | 30% |
| SP Hits Allowed | −4.0 (n=300) | −3.6 (n=190) | 63% |

The **Starved** flag needs *both* a real edge and a tiny served share, so `sp_hits` — bad,
not starved — is correctly not flagged. Separating those two is the entire point.

### The pulse compares lift, where that means anything

Cell colour was a day's rate against the market's period rate. Measured before changing it:
`batter_hit` has one bar so its base never moves (**sd 0.000**), but WNBA assists ranged
from a **.07 base to a .55 base** across days (sd 0.104) — a 40% day was coloured
identically in both, when one is outstanding and the other poor, and those are the app's
best markets. Five cells change; `batter_hit`'s change by **zero**, which is the
confirmation that the logic is right rather than merely different.

### Calibration reads the current engine only

Pooled across versions the 99-100 band showed −6.6 and looked anti-predictive; split by
engine it is +13.4 for `batter-hit-v5` alone. **A superseded scorer's calibration is not a
fact about the one running today.** Scoped, every band is positive (+14.2 → +9.3) with the
thin ones flagged. Deliberately *not* a bands × versions matrix: that yields cells of n=21
and would be its own kind of misleading.

### Two things that had been hiding shipped work

- **`element.hidden` did nothing.** It leans on the UA rule `[hidden] { display: none }`,
  which an author declaration beats at equal specificity — `.game-card` sets
  `display: flex`, `.schedule-grid` sets `display: grid`. The game-state filter, and the
  "Hide completed" toggle before it, changed their own label and hid nothing. An
  author-level `[hidden]` rule now wins.
- **Publishing could report success after failing.** wrangler errored mid-upload while
  Python's buffered prints landed *after* it, so the run read as success and the site
  served stale CSS for another twenty minutes. The exit code is now checked, and the
  publish verifies the **live URL** serves the stylesheet hashes just built — every local
  check reads `site-dist/`, the thing we just wrote, which is how a stale cache-buster
  kept a shipped header rewrite invisible for two days. The check needed two fixes of its
  own to work at all (macOS ships no CA bundle; Cloudflare 403s urllib's default agent),
  and caught a real propagation lag on its first run.

**Tradeoff.** Coverage adds a table to an already long page. It earns the space because it
is the only surface that can express "good and starved" — every other one answers a
different question.

---

## 2026-08-19 — `sp_hits` stays, unchanged; and a good market is being starved

**Decision.** Do **not** retire `sp_hits`, and do **not** change its scorer. Record
`batter_k` as under-served relative to its measured lift, pending more data.

### Retiring `sp_hits` was the wrong call, twice over

I recommended retirement on a −11.3 figure. That was one engine version inside one date
window, n=45, with a ±15 interval — **a point estimate read as a fact.** With intervals:

| slice | n | lift | 95% CI | significant |
|---|---|---|---|---|
| all `sp_hits` | 252 | −4.1 | ±6.2 | **no** |
| unders | 216 | −4.1 | ±6.7 | no |
| under 4 | 123 | −8.7 | ±8.6 | marginal |
| under 5 / 6 | 59 / 34 | **+2.4 / +1.3** | ±12 / ±14 | no |

The market is statistically **flat**, not harmful.

### The over side has real signal — that the scorer already partly captures

Prompted by the right question (*"aren't we only looking at the under?"*), I had been
measuring **36 served overs** — the scorer's choices, not the market. Over all 2,463
leakage-safe starts, ranking by the pitcher's own prior hits-allowed rate × the opposing
offence's hits/game, the top decile out of sample:

| bar | base | top decile | lift |
|---|---|---|---|
| over 5+ | .551 | .696 | **+14.4** ±10.9 |
| over 6+ | .388 | .580 | **+19.1** ±11.6 |
| over 7+ | .236 | .406 | **+17.0** ±11.6 |

Decomposed, the pitcher's own rate carries it (+10.8 alone); the opposing offence adds
~0.4 points over that, inside the noise. Durability adds little — a pitcher getting hit
gets pulled, which caps the volume.

**But no scorer variant ships.** Backtesting the *real* `_best_direction` across
over-penalties, bar sets and selectivity gates — 22 variants — the best was **+4.7 ±3.8**
against an incumbent **+4.0**. With k=22, `√(2 ln k)` ≈ 2.49 SE is the best-of-k under pure
noise; the gap is a fraction of that. The scorer already earns **+7.8** on the overs it
picks, and every attempt to concentrate them traded volume for no net gain.

**The lesson is the measurement, not the market:** an abstract feature can carry signal
that the shipping function already captures. Validate the function, not the idea.

### `batter_k` is the real finding

Judging every market on **all recorded props** rather than only those served exposes one
that is starved rather than poor:

| market | recorded | lift | served 70+ |
|---|---|---|---|
| `batter_k` | 110 | **+18.2 ±9.2** | **6** |
| `batter_hit` | 5,032 | −3.2 ±1.4 | 1,445 |
| `batter_tb` (retired) | 1,199 | −1.3 ±2.3 | 1 |

`batter_k` has the second-highest lift of any market and **has been served six times.** Its
scorer tops out at 75 with a median of 59, so it essentially cannot clear the curation
floor — the market works and the scale does not reach.

That also **vindicates the `batter_tb` retirement for the right reason**: it was retired for
never clearing the floor, and its lift is −1.3, so nothing was lost. `batter_bb` is likewise
flat (−1.3 ±10.6). Same symptom, opposite diagnosis — which is exactly why lift, not
conversion, has to be the test.

**Not acting yet.** Within `batter_k` the score does *not* discriminate — the 50-59 band
(+22.3) beats 60-69 (+17.9) on n=34 and n=68. Rescaling would serve genuinely good props
while claiming a ranking the data does not support. Worth revisiting once the sample
doubles.

**Future.** The general form of this check — *lift over base across all recorded props,
against how many actually clear the floor* — belongs on the Performance page. A market
that is good and starved looks identical to a market that is bad, until you separate them.

---

## 2026-08-19 — The NFL matchup effect is real, small, and one-sided

**Decision.** Add the opponent's measured effect to NFL player spotlights
(`services/nfl_matchup.py`), scoped to what the data supports: **negative calls only**,
for quarterbacks and running backs only.

**Reason.** The matchup pages showed each player's prop from his own recent form with no
opponent context — the obvious gap for a page meant to explain a matchup. Before building
a rating, we measured whether the opponent predicts anything beyond a player's own form.

**Defences are a real trait** (split-half r .14–.52), rated by how far players fell short
of *their own* baselines against them. Rating against league average instead would credit
a defence for having faced weak opponents.

### What it is worth splits sharply by stat

| stat | easiest-fifth minus hardest | game sd | rated |
|---|---|---|---|
| passing yards | +43 | 96.9 | yes |
| rushing yards | +10 | 39.1 | yes |
| receiving yards | +2 | 35.3 | **no** |
| receptions | +0.3 | 2.5 | **no** |
| rush attempts | +0.6 | 6.7 | **no** |

Every fantasy surface publishes a receiver matchup rating. Across three seasons here it is
worth two yards against a 35-yard game-to-game swing — below the noise floor of one game.
Usage is a coaching decision and defences do not move it at all.

### The part that nearly shipped wrong

The first working version made symmetric excel/struggle calls. Validating the *shipping*
function — not the analysis one — showed the games it flagged "excel" came in at **−0.4**
against baseline while "struggle" games came in at **−18.6**. Splitting the full spectrum:

| defence | passing yards | rushing yards |
|---|---|---|
| very tough | **−15.1 ±10.5** | **−4.0 ±3.0** |
| tough | **−21.6 ±12.9** | −2.0 ±3.2 |
| average | −3.1 ±8.6 | −0.9 ±2.4 |
| soft | −4.3 ±14.6 | +1.7 ±4.0 |
| very soft | +4.5 ±15.5 | +1.8 ±3.9 |

**A tough defence reliably suppresses. A soft one does nothing.** Every soft-side interval
covers zero, and the merely-soft passing band is negative. Game script is the plausible
mechanism: a bad defence means a lead, and a lead means running the ball and resting
starters, cancelling the matchup it created.

So there is no `excel` state anywhere in the module and a test guards that no code path
can predict an above-baseline day. A soft matchup is *named* — "soft on paper, but soft
defences have not produced above-baseline games, so we make no call" — rather than passed
off as neutral or dressed up as a rating. **"He faces a bad defence, expect a big day" is
the most common claim in football previews and this data does not support it.**

**Tradeoffs.** The page makes far fewer calls than a fantasy site would, and most players
get "not a factor". That is the product working: a stated non-finding beats a number that
is really zero. Thresholds are the bands whose interval excluded zero (−0.5 sd for
passing, −1.0 for rushing), not round numbers.

**Lesson worth keeping.** *Validate the function you are shipping, not the one you
analysed with.* The analysis used all-history ratings; the shipping version uses a rolling
window, and only re-running the measurement through the real function exposed the
asymmetry.

**Future.** Re-test once a 2026 season is ingested — three seasons is thin for the
soft-side question specifically, and a genuine positive effect at the extreme would show
up first there.

---

## 2026-08-19 — Performance is measured against base rates, not one blended average

**Decision.** Every comparison on the Performance page — markets, score bands, months,
model versions — now reads **lift over the base rate of the props it actually contains**.
The edge table is ranked by lift rather than hit rate. New module:
`services/base_rates.py`.

**Reason.** The page compared everything to the app's overall hit rate. That is a
comparison between different questions: 1+ hit lands ~61% of the time for a starting
batter, a WNBA assists line ~35%. Against one average, common events look good however
badly they are picked and rare ones look bad however well. This is [Method §1](METHOD.md)
broken on the one surface that drives retirement decisions — the project already refuses
this comparison for team records ("win percentage isn't comparable across sports") and had
simply never applied it to markets.

### It reversed the ranking

| market | served | base | **lift** | old "vs overall" |
|---|---|---|---|---|
| WNBA Assists | 68.1% | 35% | **+32.6** | +5.4 |
| WNBA Rebounds | 62.7% | 34% | **+28.5** | +3.5 |
| WNBA Points | 69.2% | 45% | **+24.0** | +6.1 |
| MLB SP Strikeouts | 58.9% | 48% | **+10.5** | −0.0 |
| MLB Batter Hits | 62.2% | 61% | **+1.5** | +0.8 |
| MLB SP Hits Allowed | 49.4% | 53% | **−3.5** | −11.5 |

**`batter_hit` has essentially no edge** — +1.5 over base, on 61% of everything served.
That is the headline finding and it was invisible before.

**`batter-hit-v5` is nonetheless a genuine improvement**: +6.9 over base against +0.0 for
its three predecessors pooled. Shrinking the recent hit rate did what it was meant to.

**The 99-100 band initially read −6.6 over base, and that was a pooling artifact.**
Corrected the same day: split by engine version, `batter_hit` at 99-100 is −1.7 across all
scorers and **+13.4 for `batter-hit-v5` alone** (n=27; +20.3 at 95-98, n=21). The negative
band belonged to the retired engines. I reported it as a live defect first — the same
mistake this entry is about, one level down: **a pooled ledger mixes engines exactly as a
blended average mixes markets.** No evidence of inversion under the current engine; the v5
samples are far too small to claim the positive either. `v3_top_band_watch` stays open on
sample size, not on evidence.

**`sp_hits` remains the retirement candidate**, and its current version is the worst row on
the board at −11.3. The old column was directionally right here by accident.

### Three ways to get a base rate wrong

- **Re-implementing resolution.** An under is `actual <= threshold`, inclusive. Hand-writing
  `<` understated the base and manufactured a +12 lift for `sp_hits` that does not exist —
  I reported that number before catching it. The module asks `domain.markets.grade`.
- **Post-hoc populations.** Filtering batters to `>= 3 PA` conditions on the outcome: a
  batter bats again partly because he reached. Base rate ranged .565→.741 across plausible
  cutoffs, flipping `batter_hit` between +4.9 and −4.5 on a choice no reader sees.
  Populations are now pre-game: the first nine batters, the first-inning pitcher, the
  WNBA `started` flag.
- **Unlike mixes.** Bands and months hold different markets (the 99-100 band is 99% 1+
  hit; league mix is seasonal). Each group is weighted by the props it holds.

**Tradeoffs.** The base rate depends on a stated population, so it is a modelled number,
not a fact — the page shows `base 35%` beside every lift so the comparison is inspectable,
and shows nothing at all when a population is unavailable rather than falling back to the
average. Ranking by lift also means the top row is no longer the highest hit rate, which
takes a moment to read; the hit rate is still the second column.

**Future.** The per-market base rates make the curation floor comparable across sports for
the first time — a 70 currently means different things in different markets. Worth
revisiting once NFL props have graded rows.

---

## 2026-08-19 — NFL props backtested properly, and a traded-player bug

**Decision.** Keep the NFL scorer's shape and its threshold ladders **unchanged**, on
measurement rather than assumption. Fix a real defect found while measuring: a traded
player was losing the history he earned elsewhere.

### The bug: a player is one player, not one player per team

`score_nfl_opportunities` grouped on `(player_id, player, team, position)`. A player who
changed teams therefore split into **per-team fragments**, and two things followed:

- Each fragment fell below the games floor, so the player was offered **no prop at all**.
  At week 3 of 2025 this hit **459 players** — Aaron Rodgers had 20 games played and 2
  under his current team.
- Each fragment was internally single-season, so the prior-season disclosure shipped the
  day before **could never fire for a traded player** — precisely the population it exists
  for. Jonnu Smith (Miami → Pittsburgh) scored 84/79 off pure Miami data, labelled Miami,
  with no mention that his whole window predated the move.

The team filter had the same shape: it filtered *rows* by team, keeping a traded player's
**old** games and discarding the team he now plays for.

**Fix.** Identity — team, position, printed name — comes from the player's most recent
game; history is every game he has played; the slate filter follows the player, not his
old rows. Jonnu Smith now reads Pittsburgh, carries `8 of these 10 games are from last
season`, and scores **69/60** instead of 84/79. Four regression tests cover it.

**This is the second time a grouping key has quietly changed a population** (the first was
MLB roster status). Worth naming as a class: *a groupby key is a claim about identity.*

### The honest numbers

Leakage-safe backtest — every player-game scored on that player's prior games only, then
compared to what he actually did. **10,552 scored player-games, base rate .542.**

| market | lift over base |
|---|---|
| rushing attempts | **+18.6** |
| receptions | **+10.6** |
| receiving yards | **+8.8** |
| passing yards | **+6.5** |
| rushing yards | **+5.2** |

At the curation floor the served population hits **.650, +10.8 over base** (n=1,081) —
the same order as MLB `batter_hit` (+11.8), not the +31 to +51 logged on 2026-08-18. That
earlier table divided by a base rate computed over *all* player-games, offensive linemen
included. **The direction was right and the magnitude was fiction**; the 08-18 entry is
annotated rather than deleted, because its reasoning about raw clear rate still holds.

### The ladders are measured now

Each rung's league-wide clear rate among genuine candidates is recorded inline in
`_STAT_MARKETS`. The ladders step down **~10 points of rarity per rung**, so "the highest
bar he still clears" is a real statement and not an artefact of round numbers. Checked for
the `batter-hit-v3` saturation defect: only 17 of 268 props sit on the top rung and one
clears it ≥80%, so no ladder is too short.

### Four alternatives lost

Cushion capped at .35, cushion dropped, consistency substituted, cushion × consistency —
tested out of sample (choose on 2023-24, evaluate on 2025). **The incumbent won on both
ship-rule terms** (+10.2 top-20% lift, +12.2 at the floor). Bands rise monotonically out
of sample: +7.0 → +10.8 → +12.8 → +17.8.

**A hypothesis I had to drop.** The full-sample band table appeared to show the top band
inverting (85-89 at +4.1, 90+ at −4.2) — the shape that forced `batter-hit-v5`. Out of
sample it is +13.6. Those buckets hold **15 props**, where the 95% interval is ±25 points;
they decide nothing. I nearly "fixed" a defect that was sampling noise.

**Version.** `nfl-props-v1` is corrected in place rather than bumped: no NFL prop has ever
been served, so there are no graded rows to separate. Version strings exist to keep a
ledger honest, and minting a v2 against an empty ledger would add a phantom row to the
Performance page forever.

**Future.** `rushing_att` at +18.6 is the standout and is the purest usage market — it
measures what a coaching staff controls rather than an outcome. If NFL props are ever
narrowed, narrow toward usage.

---

## 2026-08-11 — What the ingested odds actually taught us (and what they killed)

**Decision.** Keep odds **offline-only** — validation and benchmarking, never a surface.
Option (b) from the 2026-08-10 entry, now with evidence behind it. Also **corrects the NBA
fatigue finding logged the previous day.**

### ⚠️ Correction: the NBA back-to-back signal is fully priced

The 2026-08-10 entry called it "the first signal in this project to survive out-of-sample
validation on the first attempt". Measured against the **market** rather than against
records, it is worth nothing:

| condition | n | favourite covers |
|---|---|---|
| all games | 7,125 | 0.5033 |
| **favourite on a B2B, dog is not** | 655 | **0.4931** |
| dog on a B2B, fav is not | 1,065 | 0.4958 |
| neither | 5,080 | 0.5051 |

Every cut is within ±0.7pp of 50%. The effect is **real but already in the line** — B2B
favourites do lose more often, and the market has priced exactly that. The earlier finding
used *records* to define the favourite, which measures "is this true?" rather than "does
anyone not already know?". **Descriptive, not predictive.** Do not build on it.

### The markets are efficient; there is no edge here

Scanned NBA (7,236 games, six seasons) and CBB (10,653, two): home favourites, home
underdogs, big/small spreads, line movement, high/low totals, and CBB conference cuts.
Everything landed between **0.48 and 0.53** cover, against the ~52.4% needed to beat vig.
The largest conference deviation was 1.9 SE across ~30 conferences — exactly what chance
produces. MLB totals: 49.2% of decided bets go over. **Nothing is exploitable.**

### The benchmark, which is the real value

| | market | our records-based |
|---|---|---|
| NBA corr(spread, margin) | +0.478 | +0.098 |
| NBA picks the winner | 67.8% | 64.8% |
| MLB picks the winner | 59.5% | 56.8% |

**On "who wins" we are close to the market. On "by how much" we are five times worse.**
That is a precise statement of where a records-based read has value and where it does not.

### The finding that explains the last two days

`corr(line, |margin|)` — how well *anything* predicts a close game:

| sport | from the line | from records |
|---|---|---|
| **CBB** | **+0.531** | — |
| NBA | +0.195 | +0.098 |
| **MLB** | **+0.047** | +0.031 |

**Baseball games are close-or-not almost at random.** A toss-up MLB line averages a
3.41-run margin; a heavy favourite 3.74. The market, with every resource we lack, manages
+0.047. So the 2026-08-10 conclusion that MLB editorial cannot be calibrated was right,
and now has a cause: *the target is not predictable*, by us or by anyone. It also settles
the odds question for our core sport — **using the line would not rescue MLB editorial.**
CBB is where a line genuinely knows something, and CBB has no surface.

**The discipline this suggests.** Before shipping an editorial signal, ask whether it adds
anything the closing line does not already contain. That test just killed the fatigue
signal at zero cost, which is the whole argument for keeping odds offline.

---

## 2026-08-12 — Show the raw recent line on every prop

**Decision.** Every prop now carries `recent_line` (the actual last-10 results, oldest
first) and `line_threshold`, rendered as a compact strip under the evidence with cleared
games marked and a tally. All four live markets supply it — 448 of 448 props on the slate
it shipped against.

**Why.** A score compresses ten games into one number and hides the shape. On the day this
shipped, six props all scored 99-100 and looked interchangeable:

| player | line | cleared |
|---|---|---|
| Steven Kwan | 1 2 3 1 1 1 3 1 2 2 | **10/10** |
| Royce Lewis | 1 2 4 1 1 2 2 0 2 2 | 9/10 |
| Jonathan Aranda | 0 1 4 1 1 2 1 1 2 0 | 8/10 |
| Yandy Diaz | 1 2 0 0 2 0 0 4 3 1 | **6/10** |

Kwan and Diaz score the same and are not the same bet. **The evidence lines are our
judgement; this is the fact underneath**, and it is what lets a reader disagree with us —
which is the stated point of the product ("know what my options are… improve my
predictions"), and the "explainable, always" rule taken literally.

**Direction-aware, because the obvious version is backwards.** An *under* clears at or
below the bar. Testing `>=` would have marked a pitcher's best starts as failures — every
strong under would render as a near-total miss. `line_cleared` reads `Opportunity.direction`
rather than assuming overs.

**Grain matters more than it looks.** The batter scorer reasons per *plate appearance*, so
its raw values are 0s and 1s. Shown directly they would never match the "1+ Hit" bar the
prop is graded on. `_recent_game_line` regroups to per-game totals — the grain the prop is
actually settled at.

**Deliberately quiet.** One short row, tabular figures, low contrast, a single accent for
cleared games, and it renders nothing at all when a scorer supplies no line. A prop card
that grew a block for this would fail the experience principles; the value is that it is
scannable, not that it is prominent.

---

## 2026-08-18 — NFL props measure better than anything the app currently serves

> ⚠️ **The lift figures in this entry are wrong — superseded by
> [2026-08-19](#2026-08-19--nfl-props-backtested-properly-and-a-traded-player-bug).**
> The base rates below were computed across *every* player-game, including offensive
> linemen who never touch the ball, which made a 55% clear rate look like +51 points of
> lift. Measured against the population that can actually be offered the market, and with
> a leakage-safe backtest, the real range is **+5 to +19**. The conclusion that NFL props
> are worth building survived; the magnitude did not. Kept for the reasoning about *why*
> raw clear rate is the wrong number, which is still correct.

**Finding.** Applied the reachable-bar check to the ingested NFL seasons (78,744
player-games, 2023-2025) before building anything. **Every NFL market shows more lift over
its base rate than any market the app serves today.** Nothing built yet.

| market | served | clear rate | base rate | **lift** |
|---|---|---|---|---|
| rushing attempts | 1,314 | 58.6% | 7.5% | **+51.0** |
| passing yards | 849 | 53.9% | 4.9% | **+49.0** |
| rushing yards | 1,178 | 54.1% | 7.7% | **+46.3** |
| receiving yards | 2,020 | 50.0% | 16.0% | **+33.9** |
| receptions | 3,895 | 55.8% | 24.2% | **+31.6** |

For comparison: MLB `batter_hit` runs **+11.8** on served props, and `sp_k` overs — the
best market previously measured — **+17.0**.

**The raw clear rate is the wrong number, and it nearly misled me.** At 50-58% these look
weaker than MLB's ~65% served conversion, and my first read was that NFL props were
marginal. They are not: a 250-yard passing game happens 4.9% of the time, so predicting it
at 53.9% is an enormous edge. MLB's 1+ hit is a ~55% event to begin with. This is
[Method §1](METHOD.md) — *"a 40% hit rate on a bar that lands 15% of the time is
excellent"* — and I had to be reminded of it by my own rule.

**Why football suits the reachable-bar model.** Volume roles are stable week to week: a
lead back gets his carries, a WR1 gets his targets. That is exactly what the model needs —
`rushing_att` at +51.0 is the purest case, because it measures usage rather than outcome
and usage is what a coaching staff controls.

**Servable share is low (7-32%) and that is fine.** One NFL slate is ~16 games against
MLB's 15, but each carries far more rostered players, so even 7% of candidates is a usable
number of props. Receptions alone would serve ~3,900 across three seasons.

**Correcting an earlier claim.** I logged `nfl_props_registry` as blocked on a 2026 feed.
That is wrong: the *scorer* runs off ingested seasons and there are three of them. What is
actually missing is code — the NFL adapter has no `opportunities()` method and
`domain/markets.py` has **zero** NFL entries, so nothing is scored onto the slate,
snapshotted or graded. The 2026 feed matters for the slate↔feed **bridge** (matchup pages
for live games), not for props.

**Timing.** The regular season opens 2026-09-09, 21 days out. Registering these markets
before then means the first NFL slate is graded from week 1 rather than starting the
ledger mid-season — and a market's version history only counts forward from when it ships.

---

## 2026-08-12 — NHL market priority is backwards; goals is unservable

**Finding.** With a full 2025-26 NHL season collected (1,306 games, 47,013 skater rows,
2,755 goalie rows), the reachable-bar discipline was applied *before* building anything —
the check the architecture doc demands after total bases was scored daily for a reader who
never saw it. It reorders the roadmap.

| market | servable share | next-game clear | verdict |
|---|---|---|---|
| **goalie saves** | **99.9%** | **65.4%** | build first |
| blocked shots | 39.1% | 58.8% | viable |
| shots on goal | 32.9% | 55.3% | viable, weaker |
| points (G+A) | 20.1% | 54.1% | marginal |
| **goals alone** | **1.6%** | — | **dead** |

("Servable" = a bar exists that the player cleared in ≥60% of their last 10 games.
"Next-game clear" is leakage-safe: the bar chosen from prior games, graded on the next.)

**The roadmap had it inverted.** It lists shots on goal and points as Tier 1 with goalie
saves as Tier 2. Goalie saves is the only NHL market that is *comfortably* servable and it
converts at **65.4%** — better than the WNBA base rate of 63.7% that supports three live
markets. Points is the weakest thing worth considering at 20.1% and 54.1%.

**Goals is the total-bases shape.** Servable in **599 of 38,633** player-games. A skater
scores in 15% of games; no ten-game window makes 1+ goal a 60% proposition except for a
handful of elite forwards on heaters. Building it would mean scoring a market daily that
nobody is ever shown. **Do not build it.**

**Why hockey differs from basketball.** WNBA points/rebounds/assists accumulate in every
game — a 15-point scorer clears 10+ routinely. NHL skater events are *rare and discrete*:
a good forward takes 2-3 shots and records a point every third game. The reachable-bar
model needs a stat with a floor, and only a goalie's save count has one — they face ~25
shots whenever they start.

**Consequence for build order:** goalie saves, then blocked shots, then shots on goal.
Points last or never. This also lowers the value of NHL props overall — one strong market
plus two moderate ones, against WNBA's three — which is worth knowing before committing
weeks to it.

---

## 2026-08-12 — Two scorers shipped without their version strings; ledger corrected

**What happened.** `batter-hit-v5` (2026-08-10 18:08) and `sp-v3` (17:16) changed the
scorers but not `services/snapshots.MODEL_VERSIONS`. The 2026-08-11 slate was therefore
scored by the new engines and **recorded as `batter-hit-v3` and `sp-v2`** — 449 rows.

**Why it matters.** Version comparison is the only way this project learns whether a change
helped, and the 2026-08-08 entry already warns that it is *"only valid going forward"*.
A mislabelled slate does not merely lose one day; it silently pollutes both sides of the
comparison — the new engine's results are credited to the old one.

**Confirmed empirically, not assumed.** sp-v3's signature is threshold diversification: the
08-09 and 08-10 slates picked overs only at thresholds 7-8 (the old linear scheme's high
bars), while 08-11 spread across 4, 5, 6, 7 and 8. Same process and working tree, and v5
shipped 52 minutes before sp-v3, so both were live. The 08-10 slate (captured 11:39, before
either shipped) correctly keeps the old labels.

**Fixed.** The strings now name the shipped engines, and the 449 rows on 2026-08-11 were
relabelled. Correcting a factual recording error is not rewriting history — the scores
themselves are untouched, and leaving the label wrong would corrupt every future comparison.

**Guarded.** A test now ties each version string to a property of the scorer it names:
`batter-hit-v5` iff `_HIT_SHRINK <= 0.35`, `sp-v3` iff `_CLEAR_RATES` exists,
`wnba-pra-v3` iff the 10-game weight exceeds the 5-game. Changing a scorer without its
label now fails the suite. WNBA's string *was* updated at the time, which is why only two
markets were affected — the guard makes that the default rather than the exception.

**Add to the ship checklist:** a scorer change is not complete until its version string
moves with it.

---

## 2026-08-12 — A shared ESPN box-score collector (NBA, CBB, NHL validated)

**Decision.** `src/espn_boxscore.py` + `scripts/collect_espn_boxscores.py`. A sport is a
**`SportSpec`** — ESPN path, table prefix, stat vocabulary, columns, and the scoreboard
`groups`/`limit` it needs. Everything else is shared. Same shape as `boxscore_ingest.SPORTS`.

**Validated against an independent source, which is why NBA went first.** We hold six
ingested vendor seasons of NBA, so the collector's output can be checked against data it
has never seen. One month, 233 games, 6,064 player rows, zero failures:

| stat | exact | within 1 |
|---|---|---|
| points | **100.00%** | 100% |
| rebounds | 99.94% | 100% |
| assists | 99.96% | 100% |
| minutes | 98.28% | 100% (ESPN rounds to whole minutes) |

CBB then matched **241 of 241 games** and 99.7%+ on every stat.

**Three bugs the validation caught, all of which would have shipped.**

1. **`game_date` was the UTC instant.** A 7pm ET tip on 9 January is `2026-01-10T00:00Z`,
   so every `WHERE game_date = …` would have been silently wrong. The validation reported
   **24% agreement** until the shift was found — then 99.1%. `game_date` is now the
   league's calendar day and `start_time` keeps the instant. Same class of bug as the NFL
   bridge's one-day window; it will recur in any ESPN-sourced feature.

2. **NHL shots on goal was always zero.** ESPN ships both `S` and `SOG`; **`SOG` is a dead
   column that is always 0** and the real data is in `S`. All 1,548 skaters in a five-day
   sample had `shots_on_goal = 0` while the true values sat under a column named `shots`.
   Caught only because a team SOG of 0.0 per game is impossible — the real figure is 26.7
   against an NHL average of ~30. **Shots on goal is the headline NHL prop.**

3. **The fix for (2) dropped `g → goals` and `a → assists` from the alias map.** Worse
   than the bug: the evidence was on screen and dismissed. A debug table printed `goals`
   as `None` and it was called a formatting artifact rather than checked. The guard now in
   the suite — *every declared column must have an alias pointing at it* — is the test that
   would have caught it, and it runs for all four sports. **A column nothing maps to is
   silently always-null: the table looks right and the data never arrives.**

**Athlete id spaces are disjoint.** ESPN ids and Big Data Ball ids share **zero** of 486
NBA players (Curry is `3975` to ESPN, `201939` to the vendor — an NBA.com id). This is
fine: the collector is the *sole* source for props and never joins to vendor data. The
validation crosswalk was name-based, one-time and offline, and is deliberately not shipped.
It also demonstrated why the rule exists — "Josh Smith" played for two different teams on
2026-01-08 and the name join swapped their lines exactly (8↔22 points). Adding team to the
key took CBB agreement from 99.1% to 99.7%.

**NHL's shape.** Skaters and goalies are separate ESPN stat groups. They land in one wide
table tagged by `player_group`, keeping "one row per player-game" — the shape every scorer
in this app expects. Two tables would force every downstream query to know about both.
Goalie `saves + goals_against == shots_against` on 97.8% of rows.

**Sanity, not just agreement.** NHL has no vendor data to check against, so it was
validated against the sport itself: shots on goal 26.7 per team per game, goals 3.0,
assists 5.1, hits 19.7, blocked shots 14.6, goalie SV% .873. Every figure lands where
hockey says it should.

**WNBA is deliberately not migrated.** It is live and graded daily, with a settled schema
and a scorer reading it; rewriting it to prove a refactor would risk the one working
basketball surface for no user-visible gain. Its spec is included and exercised by the
shared parser, so the migration is available later as a separate, deliberate step.

**What this unlocks.** Player props for NHL, NBA and CBB from a source we already use, with
history back to 2011/2010/2015. It also makes the CBB and NFL **vendor feeds optional** at
player grain — a simplification, not just an addition.

---

## 2026-08-12 — `wnba-pra-v3`: back the ten-game window, drop the trend term (shipped)

**Decision.** `_RECENT_WEIGHT` (last-5 clear rate) 22 → **18**, `_BASELINE_WEIGHT`
(last-10) 18 → **22**, the `trend_score` term removed, and `_SCORE_BASE` 18 → **19** to
hold the served share. First full-scorer backtest the WNBA engine has had.

**The inputs say the weights were backwards.** Over 3,118 leakage-safe player-games — the
live formula replayed against every game using only prior ones — the **10-game** clear rate
beats the 5-game in *every* market:

| | points | rebounds | assists |
|---|---|---|---|
| `hit_l10` | **+0.159** | **+0.087** | **+0.183** |
| `hit_l5` | +0.121 | +0.053 | +0.092 |

v2 weighted the noisier window higher. Minutes, by contrast, correlate +0.067 (l5) and
+0.049 (l10) — real but well behind form, which is the **opposite** of the MLB finding and
why `batter-hit-v5` was not ported here.

**The trend term was noise.** `clip((avg_l5 - avg_l10) * 2, -5, 8)` correlated **+0.031**
with clearing — a short-window delta on noisy counting stats — while occupying up to 8
points of a 99-point scale.

**Ship rule, out of sample** (fit on the first half of the season by date, tested on the
second):

| | v2 | v3 |
|---|---|---|
| test correlation | +0.1339 | **+0.1416** |
| top-20% clear rate | 0.6923 | **0.7212** |
| spread over bottom 20% | +0.1620 | **+0.2115** |

Both halves met on held-out data, and train/test track without collapsing.

**What I did not ship, and why.** A variant also cutting `role_score` 25 → 20 scored best
in aggregate (test corr +0.1482) but moved per-market results in different directions —
better assists, worse rebounds. With ~500 props per market in the test half that is not
separable from noise, so the simpler change wins.

**An aggregate pass can hide a per-market regression.** Points' top-20% appears to drop
(0.7317 → 0.7049), which looked like a real cost until sized: the test-half points top
quintile is ~121 props, so that gap is **0.6 SE**. Worth checking every time — the
aggregate was carried by assists and rebounds either way.

**`_SCORE_BASE` is a matched pair with the dropped term**, exactly as v5's rescale was:
removing 8 points of headroom would have cut the served share 42.9% → 38%. At 19 the share
holds (41.1%) and the served clear-rate still improves (0.6998 → 0.7067). Do not change one
without re-tuning the other.

**Correcting an earlier note.** The tracker suggested v2 might *under*-weight form because
`recent_score` capped at 22 against `role_score`'s 25. That compared one term to the whole:
form is spread across `recent + baseline + cushion + trend`, up to **63** points against
role's 25. Form was never under-weighted — it was *mis*-weighted, backing the wrong window.

---

## 2026-08-12 — ESPN can supply player props for NHL, NBA and CBB. Feasibility confirmed

**Finding.** Everything needed for player props in **NHL, NBA and CBB** is available from
the same ESPN `summary` endpoint the WNBA collector already uses
(`.../sports/<path>/summary?event=<id>` → `boxscore.players`). No vendor purchase, no new
provider. Nothing built yet.

**What each sport returns**, with athlete ids on every row:

| sport | stats |
|---|---|
| **NHL skaters** | TOI (plus PP/SH/ES splits), shifts, G, A, **SOG**, blocked shots, hits, takeaways, giveaways, faceoff W/L/%, PIM, +/− |
| **NHL goalies** | saves, shots against, GA, SV%, ES/PP/SH saves, TOI |
| **NBA** | MIN, PTS, FG, 3PT, FT, REB (+OREB/DREB), AST, TO, STL, BLK, PF, +/− |
| **CBB** | as NBA, without +/− |

This covers **every prop the roadmap wants for NHL** — shots on goal, points (G+A), goalie
saves, and blocks/hits as stretch markets — and the full P/R/A set for NBA and CBB.

**History is deep, not live-only.** Box scores resolve back to at least **2011 (NHL)**,
**2010 (NBA)** and **2015 (CBB)** — checked by pulling a real game's box score on each date,
not by trusting that the schedule endpoint answered. So these are backfillable archives,
which matters: [Method §2](METHOD.md) needs multiple seasons to split-half anything.

**Effort is a generalisation, not a new build.** `src/wnba_collector.py` is 671 lines and
roughly 80% of it is sport-agnostic — request/retry, schedule paging, the stat-name
cleaners, `_made_attempted`, `_minutes_float`, athlete-id extraction, incremental
skip-existing, upsert. The sport-specific parts are the ESPN path, the stat-name → column
map, table names, and the season window. That is the same shape as
`boxscore_ingest.SPORTS`: one shared engine, a spec per sport.

**Difficulty order, and it is not intuitive.** NBA and CBB are near-clones of WNBA — same
stat vocabulary, same single athlete group. **NHL is the awkward one**: skaters and goalies
are two different stat sets in separate groups, so the "one row per player-game" shape
needs a decision (two tables, or one wide table with nulls). NHL also has no vendor data at
all, so its collector *is* its data source, where NBA/CBB have ingested seasons to
cross-check a collector against — a real validation advantage worth using.

**Volume, for planning.** One summary call per game. NHL and NBA are ~1,300 games a season
(~20 minutes of backfill each at a courteous rate); **CBB is ~6,300** (~2 hours per season).
Daily incremental is 5-15 games for any of them. The existing collector already skips
completed games it holds.

**Not decided here:** whether to build any of it. This entry answers "is it possible and
what would it cost", so the sequencing decision can be made on facts.

---

## 2026-08-11 — ESPN scoreboard groups and limits (college sports only)

**Decision.** `src/espn_scoreboard.fetch` accepts `groups` (fetch several, union by event
id) and `ScheduleOnlyESPN` gains `espn_groups` / `espn_limit`. **No shipped league changes
behaviour.** This is plumbing a CBB adapter will need, plus a documented trap.

**What prompted it.** Building toward CBB Phase 0, ESPN returned 11 games on a date our
own feed had 22. It gets worse on busy nights — **19 of 169**. The default scoreboard is a
subset, and the response truncates to `limit` after filtering, so `groups=50` alone still
capped at 100. `groups=(50,)` with `limit=300` matches our vendor feed exactly on every
date checked (54/54, 149/149, 169/169).

**A wrong turn worth recording.** My first probe used `limit=900` and NCAAF came back as
exactly 25 on three separate Saturdays, which reads unmistakably like a cap — quiet
Tuesdays correctly returned 2. I very nearly logged "our NCAAF adapter silently truncates
every Saturday" as a live bug. It is not: **ESPN handles large limits badly**, and at the
adapter's actual `limit=100` the same date returns **45**. The lesson is the same one as
the pace leak — when a number looks alarming, check the instrument before the world.

**NCAAF deliberately unchanged.** Its default returns FBS, which is what this product means
by college football. Adding FCS (group 81) is now one line and would take a November
Saturday from 45 games to 99 — complete, but mostly lower-division games nobody asked for.
Left alone, with the option documented in the adapter.

**Tests** cover the union-and-deduplicate behaviour, one group failing without losing the
others, total failure still returning `[]`, and that no shipped adapter declares groups.

---

## 2026-08-11 — CBB editorial: green light, but as a *filter*, not a ranker

**Decision.** CBB Phase 1 is viable — records genuinely predict competitiveness there,
unlike MLB. But the signal's real use is **excluding blowouts**, not identifying great
games, and it must not be sold as insight. Measured on 7,449 D1-vs-D1 games with 8+ prior
games for both sides.

**Test A — do records predict competitiveness?** Yes, and by a wide margin over baseball:

| | CBB | MLB |
|---|---|---|
| corr(record gap, \|margin\|) | **+0.2367** | +0.031 |

| signal | n | within 5 pts | vs base (31.1%) |
|---|---|---|---|
| **mismatch (gap ≥ .40)** | 880 | 19.2% | **−11.9pp** |
| close records (gap ≤ .10) | 2,377 | 34.5% | +3.4pp |
| both poor (max < .400) | 1,030 | 33.0% | +1.9pp |
| **both good (min ≥ .650)** | 862 | 28.8% | **−2.4pp** |

**Two findings that shape the design.**

**Quality is inverted here.** "Both good" makes a game *less* likely to be close — the
exact opposite of the MLB `even` rework, which added a quality gate because closeness alone
predicted nothing. In CBB only the **gap** matters, and adding a quality requirement would
make the signal worse. A lesson that transfers between sports is the exception, not the
rule (see also: v5 not porting to WNBA).

**Exclusion is much stronger than selection.** Mismatch detection moves the within-5 rate
by −11.9pp; the best *positive* signal moves it +3.4pp. Detecting a bad game is roughly
three times more reliable than detecting a good one.

**Test B — does any of it survive the line?** Mostly not:

| | corr with \|margin\| |
|---|---|
| closing line | +0.3952 |
| records alone | +0.2368 |
| **records, after controlling for the line** | **+0.0664** |

And by bucket, records add nothing precisely where it would matter — |spread| 0-2 gives
−0.003, 5-7 gives −0.034 — while the only bucket with real residual signal is |spread|
11-44 at +0.220. **In the close games anyone wants to watch, records tell us nothing the
market has not already priced.** They distinguish a 20-point blowout from a 35-point one.

**Why this is still a green light.** [Method](METHOD.md) rule 6 exists to stop us claiming
*edge*, and by that standard CBB editorial has none. But the product does not use odds and
is not betting: the question for curation is "does this help a reader decide what to
watch, from evidence they can see?" — and a 15-point within-5 spread between mismatches and
close-record games does. What we must not do is present it as insight the market lacks.

**What it changes in the plan.** [CBB](CBB.md) Phase 1's curation gate should lead with
**exclusion** — drop the ~12% of the slate that records identify as likely blowouts — rather
than trying to crown a best game from 100 candidates. That is both the stronger signal and
the better answer to the volume problem. Use the record **gap** only; do not add a quality
gate.

---

## 2026-08-11 — Totals: no readable signal in any sport. Question closed

**Decision.** Stop looking for an over/under edge. Scanned MLB, NBA and CBB with ~45
splits including every classic angle; nothing survives. **Do not re-run this** without a
genuinely new data source.

**What was tested.**

| sport | splits | best survivor |
|---|---|---|
| MLB (6,424 games) | temperature (4 bands), wind speed + direction, sky, day/night, total size, **71 home-plate umpires** | none |
| NBA (7,166) | prior pace, back-to-backs, line movement, total size, spread size, season | none, max +2.2 SE across 18 splits |
| CBB (10,612) | prior pace, line movement, total size, **29 conferences** | steam-following, inside the vig |

**The classic angles are priced.** Weather was the most promising prior — hot air carries,
wind blows balls out — and MLB temperature bands came in at −1.5, −2.2, +0.1, +0.6 SE. Wind
direction, all under 1.8 SE. The market knows the forecast too.

**Umpires do not have a persistent zone effect *in this data*.** The extreme looked
compelling — Roberto Ortiz's games went under 69% of the time (−3.2 SE). Then: across 71
umpires the largest |SE| expected from chance alone is ~2.9, his split by season is
0.571 / 0.286 / 0.250 / 0.375, and **split-half persistence across all umpires is
r = +0.057** — the platoon-splits test, and the same near-zero answer.

**The one directionally consistent result, and why it still is not enough.** CBB totals
that moved **down** 3+ points went under 54.8% (2024) and 52.9% (2025) — same direction
twice, and "follow the steam" is a real mechanism rather than a fitted number. But 53.6%
overall against a ~52.4% vig break-even puts the entire edge inside the noise band.

**Conference tendency is the one open thread.** Over/under rates correlate
**r = +0.2518** between the two CBB seasons across 29 conferences — far above umpires. But
with n=29, `SE(r) ≈ 1/√26 ≈ 0.196`, so that is **~1.3 SE from zero**: suggestive, not
significant, and two seasons cannot settle it. Revisit only if more CBB seasons land.

### The methodology notes worth keeping

**A huge effect in an efficient market is a leak.** NBA fast-pace games went over 61.4%
(+9.7 SE) — using `pace` computed *from the game itself*. More possessions → more points →
over. Circular. Re-run with each team's **prior** pace: +1.3 and −1.1 SE, nothing. Any
result that large should trigger a leakage check before a celebration.

**Expected max deviation from chance is `√(2 ln k)` for k splits.** Across 71 umpires that
is ~2.9 SE, across 29 conferences ~2.6. Computing it *before* looking at the extremes
turned three "findings" into what they were. MAAC's under rate was 53.0% then 64.9% by
season — the whole effect was one year.

**Split-half persistence is the test that keeps working.** It killed platoon splits
(+0.077), umpire zones (+0.057) and MAAC, and it is what separated a real conference
tendency (+0.252) from a one-season artifact.

---

## 2026-08-11 — MLB market lines reconciled across two feed vintages

**Decision.** `services/mlb_odds.py` interprets the MLB box-score odds. It **reads**; it
does not rewrite `mlb_box_team_games`, which stays faithful to the source.

**The problem.** I first reported MLB odds as "2023 only, 1,627 rows". Wrong —
2020-2022 carry odds too, in a shape that made them look empty:

- **2020-2022** pack *two different quantities into one column*, split across the game's
  two rows: one carries the game **total** (4.5-14.0), the other the favourite's
  **moneyline** (always negative, -107 to -480). It is **not** home/road consistent, so
  position cannot disambiguate it — a positional rule would mislabel half the season.
- **2023** uses a richer layout: per-team moneylines, and a total carried as text with its
  juice (`"o7.5 -122"`).

**The fix.** Magnitude, not position. The two ranges do not overlap, and over 5,886 games
**every single one** has exactly one value in each band. Validated against outcomes: the
row we label favourite wins **59.5%**, consistent across all four seasons (0.574-0.604) —
which is what a -150ish favourite should do, and would be ~0.50 if the attribution were
wrong.

**What we deliberately do not produce.** For 2020-2022 the vendor prices only the
favourite, so the underdog's moneyline stays `None` rather than being derived — publishing
a number the vendor never did is inventing data. No MLB season here carries a closing
spread; baseball's equivalent is the runline, which ships as text.

**Result.** All four seasons usable: 6,713 games with a total, 7,513 team-rows with a
moneyline — up from the 1,627 I had written off.

---

## 2026-08-11 — NFL feed pickup joins the daily run (Downloads only)

**Decision.** `services/nfl_feed_refresh.refresh()` runs inside the daily `rebuild()`. If a
team+player feed pair is sitting in `~/Downloads` it is imported; otherwise nothing
happens and nothing is said.

**Reason.** The slate↔feed bridge shipped the same day works on *loaded* seasons. Keeping
the current season loaded meant remembering to run `scripts/import_nfl_feed` by hand every
week — the gap between "the bridge works" and "the bridge works on this year's games".

**Idempotent by fingerprint.** The rebuild is daily and an NFL player feed is ~9MB.
Re-parsing an unchanged workbook every morning is pure waste, so each import records the
source files' name+size+mtime and a matching run short-circuits before opening the file.

**Downloads only — and the first version got this wrong.** It reused the CLI's search
path, which also walks `~/Documents`, and on the very first run it found a feed in a
personal `to review` folder and imported it. Harmless (it re-loaded a season already held)
but wrong in principle: **an automated daily job must not go hunting through someone's
documents and load whatever it finds.** Downloads is the drop location the MLB pipeline
already uses, so a file arriving there means "load me". The manual CLI keeps the broader
search, because a human invoking it has named the file.

**Non-fatal.** A malformed NFL workbook must never take down the MLB daily update, so the
pipeline records `nfl_error` and continues — same contract as WNBA and MLS. Note this
composes with the drift guard shipped alongside: bad layout raises, the pipeline notes it,
and no half-loaded season is written.

---

## 2026-08-11 — NFL slate ↔ feed bridge: join on date + teams, never on ids

**Decision.** `services/nfl_bridge.py` matches a live ESPN NFL game to its row in the
ingested vendor feed, so a slate game whose season is loaded opens the same matchup page
the archive serves. `views/game.py` gains an NFL branch; `NFLAdapter.supports_deep_dive`
becomes True with a **per-game** `deep_dive_available()` gate.

**Why it was hard, and what actually worked.** The two halves share no identifier — ESPN
uses event ids (`401772980`), the feed uses `46033-SFO@PHI`. The tracker framed this as
needing to decode the vendor key. It does not: **both sides carry full team names**, so
the join is `(date, home team, away team)` and the `AWAY@HOME` string is never parsed.
Names normalise through the feed's own `nfl_teams` dimension (long/short/nick/initial), so
a rebrand or a nickname-only schedule still resolves, and an ambiguous name resolves to
nothing rather than to a guess.

**Two things that would have silently broken it.** Week is *not* a join key — ESPN calls a
wild-card game "week 1 of the postseason", the feed calls it week 19 of the season, and
joining on it would match nothing in January. Dates need a one-day window, because ESPN
start times are UTC and a Sunday-night kickoff records as Monday. Both are pinned by tests.

**`None` is a normal answer.** The feed holds regular season and playoffs only, so
preseason *never* matches, and an un-ingested season never matches. Rather than a bare
failure, `unavailable_reason()` names the cause — "not preseason", or "the 2026 season is
not loaded yet; the feed holds 2023, 2024, 2025" — because the feed's coverage is a fact
the reader can act on.

**Capability vs availability.** `supports_deep_dive` stays a league-level flag, and a new
optional `deep_dive_available(game)` decides per game. Cards consult it before rendering a
"Matchup →" link, so we never offer a link that lands on "analysis is not connected yet".
That is the honest-data rule applied to navigation.

**What this does *not* unblock.** NFL props still cannot be scored or graded. The 2026
season cannot be ingested until its games are played, so today's cards will not deep-dive
until a mid-season feed lands. `nfl_props_registry` remains blocked — but on **data
cadence**, not on missing code, which is a clearer place to be stuck.

---

## 2026-08-11 — NFL feed drift fails at import instead of months later

**Decision.** `src/nfl_ingest` declares `REQUIRED_TEAM_COLUMNS` / `REQUIRED_PLAYER_COLUMNS`
and refuses a workbook missing any of them, naming every missing column and the file.

**Reason.** The header flattener derives column names from whatever the workbook carries.
That is what makes it robust — and exactly why it cannot detect drift: a renamed vendor
category yields a *renamed column*, not an error. The table looks fine and a matchup page
breaks months later. Only naming what we depend on can catch it. The contract is
deliberately not a schema mirror: identity, the joins, and the stats the matchup page and
prop scorer read.

**It immediately found something.** The existing synthetic test fixtures did not carry
`venue`, `final`, `first_downs`, `total_plays`, `position`, `opponent` or the receiving
group — so the ingest tests had been exercising a workbook shape the real feed never has.
Fixtures updated to be faithful; the 2023-2025 feeds load clean against the new contract.

---

## 2026-08-10 — "Volume beats form" is baseball-specific. Do not port v5 to WNBA

**Decision.** Record that the `batter-hit-v5` lesson **does not transfer**, and change
nothing in `src/wnba_opportunity.py` on this evidence alone.

**Why it needed checking.** v5 cut MLB's recent-form weight to 0.25 after finding plate
appearances predict a 1+ hit more than twice as well as recent hitting. The obvious next
move is to do the same to the WNBA scorer, where minutes are the analogue of plate
appearances. The obvious next move is wrong.

**Measured on 1,437 leakage-safe WNBA player-games** (prior 10 games, at the reachable bar
the scorer would actually pick):

| input | points | rebounds | assists | pooled |
|---|---|---|---|---|
| **recent clear rate** | +0.2710 | **+0.3835** | +0.2434 | **+0.2999** |
| minutes, last 5 | +0.1974 | +0.0980 | +0.2394 | +0.1800 |
| recent average | **+0.3073** | +0.3649 | +0.2179 | +0.1487 |

**Recent form beats volume roughly 5:3 overall, and nearly 4:1 for rebounds** — the exact
inverse of baseball.

**Why the sports differ.** A 1+ hit is near-binary at ~0.21 per plate appearance, so the
spread in true talent is small and the number of chances dominates. Points and rebounds
are counting stats where role and ability genuinely separate players: an 18-point scorer
is a different thing from an 8-point scorer in a way that a .270 hitter is not from a
.245 one. The MLB finding was about a *hard binary event*, not about volume in general.

**What this implies, unshipped.** If anything the WNBA scorer may **under**-weight form —
`recent_score` caps at 22 against `role_score`'s 25. But the score is a compound of six
terms, several of which encode form indirectly (`baseline_score`, `cushion_score`,
`trend_score`), so an input-correlation table is not enough to justify a reweight. That
needs a full-scorer backtest on more than 1,437 rows. Logged as a candidate, not a change.

**The general lesson.** Today's method — decompose which inputs actually predict the
outcome, then reweight — is sound and portable. Its *answers* are not. Re-measure per
sport and per market before assuming a finding carries.

---

## 2026-08-10 — `batter-hit-v5`: chances beat form (shipped)

**Decision.** `_HIT_SHRINK` 0.70 → **0.25**, with the score scale re-tuned from
`(est-0.45)/0.37` to `(est-0.550)/0.225` so the served share holds. One change, two
matched constants.

**The finding, on 28,000 leakage-safe batter-games from our own feed:**

| input | correlation with getting a hit |
|---|---|
| **plate appearances per game** | **+0.1296** |
| recent per-PA hit rate | +0.0539 |
| recent strikeout rate | −0.0494 |

**How many chances a batter gets predicts a 1+ hit more than twice as well as how well he
has been hitting.** v3 weighted recent form at 0.70 of its deviation from the mean; the
data says it deserves far less. This is the same lesson as the batting-order analysis
earlier today — that slot's huge raw spread was 86% composition, i.e. plate appearances —
arriving from the other direction.

**Validated out of sample** (fit on the first half of the season, tested on the second),
with train and test tracking closely at every setting:

| | shrink 0.70 | shrink 0.25 |
|---|---|---|
| test correlation | +0.1127 | **+0.1314** |
| served (70+) conversion | 0.6304 | **0.6417** |
| top-20% conversion | 0.6419 | **0.6556** |
| spread over bottom 20% | +0.1613 | **+0.1879** |

**Both halves of the ship rule are met** — the top lifts and the spread widens — on held-out
data. The trend is monotonic down to ~0.10 rather than a picked optimum; 0.25 was chosen
over the peak because a score that shrinks 90% of recorded form away is hard to defend
beside evidence lines that quote that form. Explainability bought ~0.001 of correlation.

**Tradeoff.** The 90-100 band does not improve (0.6642 → 0.6545 in-sample); the gains are
in 80-89 (0.6491 → **0.6701**) and in the spread. That is consistent with the separate
finding that the top band is this market's weak spot, and `v3_top_band_watch` stays open.

**`_LEAGUE_HIT_RATE` was deliberately left at 0.25 although it is wrong.** The true per-PA
rate in our own data is **0.2092**; 0.25 is nearer a batting average (hits per official
at-bat, 0.2347). It reads as a round-number placeholder. But shrinkage is linear, so the
constant sets the score's **zero point, not its ordering** — corrected in isolation and
re-scaled, test correlation moves +0.1119 vs +0.1137, i.e. nothing. It is entangled with
the scale constants and changing it alone silently cut the served population from 19% to
13%. Documented in place; do not "fix" it without re-tuning the pair.

**Method note.** The first comparison said the correction made things *worse* — because it
changed the league rate while leaving a scale that had been tuned around the old one. Any
future change to these constants has to re-tune them together or the comparison is
meaningless.

---

## 2026-08-10 — `batter_hit` top band: quantified, not fixed

**Decision.** Record what the lift lens says about the flagship market, and **ship
nothing.** The suggestive result did not survive an attempt to reproduce it.

**What the ledger says.** On the 792 graded rows where a confirmed lineup slot is known —
so each prop can be compared to *its own slot's* base rate rather than a flat league
average — discrimination rises cleanly and then inverts:

| band | n | converted | slot-adj base | lift |
|---|---|---|---|---|
| <70 | 533 | 0.578 | 0.573 | +0.005 |
| 70-79 | 115 | 0.617 | 0.598 | +0.019 |
| **80-89** | 68 | 0.677 | 0.613 | **+0.064** |
| **90+** | 76 | 0.487 | 0.611 | **−0.124** |

An era offset is normalised out first (2026 offence runs ~0.021 below the 2020-24 base
rates), and the slot curve itself validates against this season — slot 1 observed 0.656
against 0.669 predicted, slot 9 observed 0.465 against 0.470. The 99-100 sub-band is
−0.19 at 2.2 SE. **80-89 is the app's best band, not 90+.**

**The mechanism looked clean.** The 90+ band is not thinner-sampled (stability 87.4,
in line with every other band) — it selects **extreme recent form**: a mean last-25 per-PA
hit rate of **0.340** against a league 0.217. And `_HIT_SHRINK` is a *fixed multiplier*,
blind to sample size: a 25-PA rate and a 200-PA rate are shrunk identically, when a
25-PA 0.340 should regress almost to the mean. Proper Bayesian shrinkage
(`(raw·n + league·k)/(n+k)`, the form already used for pitchers in
`opposing_starter_note`) was the obvious fix.

**It did not reproduce.** Simulated on 136,564 leakage-safe batter-games, v3's fixed
shrink shows **no inversion at all** — 0.546 / 0.640 / 0.652 / 0.681, monotonic. Bayesian
shrinkage is marginally better per band but collapses the top of the range: at k=100 only
159 props reach 90+, at k=200 just two. A fix for a problem that a 136k-row simulation
cannot see, which also guts the score range, is not a fix worth shipping on n=76.

**Where that leaves it.** The ledger signal is real enough to watch and too thin to act on.
Re-check once the 90+ band has a few hundred graded confirmed-lineup rows. Until then
`v3_top_band_watch` stays open, now with a number attached instead of "1-4 (n=5)".

**One concrete discrepancy found on the way.** `_LEAGUE_HIT_RATE = 0.25`, but the measured
per-PA hit rate across 144k batter-games is **0.2172** — the scorer shrinks toward a mean
about 15% too high, which biases every shrunk rate upward. The two may be measuring
different denominators (`plate_appearances` vs box-score `bat_pa` treat walks/HBP/sac
differently), so this needs verifying before changing. Worth doing: it sits under every
batter score.

---

## 2026-08-10 — `sp-v3`: threshold impressiveness from real rarity (shipped)

**Supersedes the "why nothing shipped" paragraph in the entry below.** That paragraph
judged the candidate on **raw conversion**, which is the very mistake the entry itself
identifies. Re-scored on **lift over base rate**, the fix is a clear win and the three
"interacting decisions" collapse to one.

**Decision.** `_best_direction` now takes each threshold's impressiveness from measured
league clear-rates (`_CLEAR_RATES`, 14,188 starts of 2020-24 box-score history) instead of
`1 - (t-lo)/span`. **The `sp-v2` over-penalties are unchanged, and `sp_hits` is not
retired** — neither turned out to be necessary.

**Evidence** — 45,020 leakage-safe simulated starts (prior 6 starts only), lift over base
rate by score band. Rarity beats linear in **every band of both markets**:

| band | `sp_k` linear → rarity | `sp_hits` linear → rarity |
|---|---|---|
| 60-69 | −0.096 → **+0.056** | −0.078 → **−0.017** |
| 70-79 | +0.019 → **+0.130** | **−0.037 → +0.047** |
| 80-89 | +0.094 → **+0.215** | +0.015 → **+0.095** |
| 90+ | +0.184 → **+0.346** | +0.085 → **+0.104** |

Both remain monotonic, so this is stochastic dominance rather than a reshuffle. The
`sp_hits` 70-79 row is the headline: the old scorer was serving props with **negative
lift** — worse than betting the base rate blindly — inside the curation floor.

**Why the over-penalty did not need touching.** At 0.45 / 0.70 / 1.00 the served lift
moves by ~0.01 once impressiveness is right. `sp-v2` was compensating for a distortion
that made high-threshold overs look artificially attractive; fix the cause and the
penalty stops mattering. A logged decision that no longer does harm is left alone.

**Tradeoffs.** Served volume falls ~25-40% — fewer, better props, which the curation floor
already implies. `sp_hits` **narrows** its lift spread (+0.163 → +0.120) even while every
band improves, because its 90+ population collapses to n=65; the ship rule's "widen the
spread" is technically not met there, and band-wise dominance was judged the stronger
evidence. Base rates are 2020-24 and will drift; they are a documented constant, not a
live query, so they need periodic re-measurement.

**Live check.** On the 2026-08-10 slate the scorer now spreads across `≤4`/`≤5` and real
overs instead of jamming `≤4`, and the top score fell from 94 to 87. Bryce Elder's "5 or
fewer hits allowed" moved **94 → 84** — much closer to his measured 0.619 baseline than the
6-start window implied, which is exactly the correction intended.

**A test caught a real bug.** The fallback for an unmeasured threshold was unclamped: a
bar of 99 against a 4-8 range returned **−22.75** and would have poisoned the argmax.
Clamped to [0, 1].

---

## 2026-08-10 — Judge a prop by lift over base rate, not by conversion rate

**The lens.** A 40% hit rate on a bar that lands 15% of the time is excellent. A 56% hit
rate on a bar that lands 54% of the time is worthless. The app has been evaluating SP
props by **raw conversion**, and that single choice distorts three separate decisions.
Measured on 416 graded SP props against 2020–24 base rates:

| market | dir | n | converted | base rate | **lift** | verdict |
|---|---|---|---|---|---|---|
| `sp_k` | over | 38 | 0.395 | 0.224 | **+0.170** | real edge |
| `sp_k` | under | 170 | 0.629 | 0.565 | **+0.065** | real edge |
| `sp_hits` | under | 189 | 0.561 | 0.572 | −0.011 | no information |
| `sp_hits` | over | 19 | 0.158 | 0.253 | −0.095 | actively bad |

**1. `sp_hits` carries no information — a retirement candidate.** At 85+, where the app
actually recommends, it converts 0.524 against a 0.542 base rate for the thresholds it
picked. Betting the base rate blindly does as well. This is the total-bases shape again:
it looks respectable at 56% until you ask 56% *of what*.

**2. `sp-v2` penalised the app's best signal.** That refit cut overs (`sp_k` ×0.70,
`sp_hits` ×0.45) because overs converted 0.395 against unders' 0.629. But that compares
overs to unders, not to their own difficulty. `sp_k` overs sit at **+0.170 lift, the
highest of any SP cell** — and +0.339 at 85+. The penalty is suppressing the one thing
that works. `sp_hits` overs deserved theirs (−0.095).

**3. `_best_direction`'s "impressiveness" is linear in the threshold's value, not its
difficulty.** For an under it is `1 − (t−lo)/span`, so `≤4` scores 1.00 while actually
happening 46% of the time, and `≤8` scores 0.00 while happening 95% of the time. Since
value = clear-rate × impressiveness, the hardest bar wins the argmax on impressiveness
alone. The ledger shows the consequence exactly:

| threshold picked | n | converted |
|---|---|---|
| `≤4` | 96 | 0.375 |
| `≤5` | 61 | 0.672 |
| `≤6` | 32 | 0.906 |

It picks the hardest bar most often, and that bar converts worst.

**Why nothing shipped.** Replacing impressiveness with true rarity was backtested on
45,020 leakage-safe simulated starts (prior 6 starts only). It is **not a clean win**:
isolated to unders it lifts `sp_k` 85+ from 0.685 to 0.742 but `sp_hits` only 0.616 to
0.624, and it cuts served volume by ~85%. Its headline gains come from flipping the mix
to overs — which is entangled with `sp-v2` and cannot be judged independently of it.
Shipping would reverse a logged decision on simulated evidence while the real graded
evidence points the same way for `sp_k` but the opposite way for `sp_hits`.

**Three decisions, none of them mine to make alone:** retire `sp_hits`; drop or invert
the `sp_k` over-penalty; re-base impressiveness on real rarity. They interact, so they
should be taken together, and `sp_hits` retirement should follow the total-bases pattern
(delete the scorer, keep the `MarketSpec` and grading branch so old ledger rows resolve).

**How this surfaced.** From a live bet, not a code review: a pitcher scored 90/94 on a
strikeout under whose own career rate was *below* league average. The hypothesis — that
the pitcher scorers do not shrink recent form the way `batter-hit-v3` does — was
**wrong**: score and outcome correlate +0.140 and the bands are monotonic. The real
problem was the denominator, not the shrinkage.

---

## 2026-08-10 — Park factor is a real, unused input; batter-specific park effects are not

**Decision.** Record that **ballpark** shifts P(1+ hit) materially and persistently, and
that **batter × park** does not. Nothing built yet.

**Evidence.** Split-half across 2020-21 vs 2022-24, 30 parks with 1,500+ batter-games:

- **Park effect: r = +0.413.** Range **12.0 points** of P(1+ hit) — Boston +6.9 and
  Colorado +6.4 against Milwaukee −5.1 and the Dodgers −4.0, on a 0.559 league rate.
- **Batter × park (beyond the park's own effect): r = +0.047.** Noise. "He hits well at
  Coors" is a story, not a signal.
- Batter home/road split: r = +0.127 — weak, marginal.
- Batter vs individual pitcher: only 26 pairs reach 12 meetings in five seasons.
  Untestable here, and unavailable in practice for a given night's matchup.

**Why it looked promising.** `batter-hit-v3` uses no park context at all, and 12 points
of range is large next to what the model does use.

**Backtested against the ledger the same day — and it does not transfer. Not built.**
Across 2,714 graded `batter_hit` props with a park factor attached:

- `corr(park factor, win)` = **+0.025**; after removing the app's own score, **+0.033**.
- By tercile: pitcher parks 0.556, neutral 0.586, hitter parks 0.568 — **not monotonic**.

This is well powered enough to be a real negative. A full-strength park effect predicts a
~7.3-point spread across those terciles; the observed spread is 1.2 points against a
standard error near 1.6. The obvious rescue — that a batter's recent rate already embeds
their home park, so the effect should only bite on the road — is also wrong: road batters
show *less* park sensitivity (+0.017) than home batters (+0.032), the reverse of that
prediction.

Most likely the historical park factor is a run-environment effect that does not survive
into "does this batter get **at least one** hit", which is dominated by plate appearances
and batter quality. Possibly also an era gap (2020-24 factors, 2026 slate).

**Incidental, and worth keeping:** home field is worth essentially **nothing** on
P(1+ hit) — 0.5580 at home vs 0.5601 on the road across 144k batter-games. Do not add
"playing at home" as batter evidence; it is not evidence.

**Also checked: batting order.** The raw spread is enormous (0.669 at slot 1 to 0.470 at
slot 9), but **86% of it is who bats there**. Controlling for the batter's own rate leaves
~1.8 points, confirmed within-batter for players who moved around the order. The existing
±3 `slot_bonus` is about right. **Validation, not a bug** — and a reminder that a large
raw split is usually a composition effect.

---

## 2026-08-10 — NBA upsets: fatigue is a real, replicating signal

> **⚠️ Superseded 2026-08-11 — see "What the ingested odds actually taught us".** Measured
> against the **market** instead of against records, this signal is worth nothing: B2B
> favourites cover 49.3%, within noise of 50%. The effect below is real and it replicates;
> it is also entirely priced into the closing line. Descriptive, not predictive. **Do not
> build on it.** The entry stands as written because the measurement was correct — the
> *question* was wrong.

**Decision.** Record the first signal in this project to survive out-of-sample validation
on the first attempt. Nothing built — NBA is schedule-only.

**Evidence.** 3,685 NBA games with a clear favourite (record gap ≥ .10), base upset rate
30.1%:

| condition | n | upset rate | vs base |
|---|---|---|---|
| underdog at home **and** favourite on a back-to-back | 268 | **42.9%** | **+12.8** |
| favourite on a B2B, underdog is not | 469 | 38.4% | +8.3 |
| underdog at home | 1,856 | 34.8% | +4.6 |
| underdog on road, favourite rested | 1,532 | 24.7% | −5.4 |

An 18-point swing between best and worst. **It replicates**: split across 2018-21 and
2024-25, the B2B cut gives +8.4% and +8.0%, the combined cut +13.8% and +10.6%.

**Contrast with the editorial finding.** Records alone say nothing about whether an MLB
game will be close. Rest state says a great deal about whether an NBA favourite will lose.
Fatigue is mechanistic where "evenly matched" was not.

**Nearly missed.** `team_rest_days` is text (`B2B`, `3IN4-B2B`, `3+`), so a numeric parse
silently dropped every back-to-back and returned nothing. The first pass reported no
effect. Worth remembering the next time a promising column returns a flat result.

---

## 2026-08-10 — Three negative results from the box-score history

Full evidence in [Historical Data](HISTORICAL_DATA.md) §3. Summarised here because each
one **closes** a line of work.

**1. Platoon splits are not a stable trait — question closed.** The 2026-08-09 entry
rejected them as "too thin here, not does not exist", flagging a re-test if multi-season
history landed. It landed: 127,886 batter-games, 2020–2024, with the opposing starter's
hand. The effect is now measurable (5.5% of batters exceed a .040 split at k=200, against
0.0% before) but it does not **persist**: split-half correlation between 2020-21 and
2022-24 is **r = +0.077**, against **r = +0.576** for overall hit rate measured the same
way on the same players. More seasons will not change this; only a different kind of data
(career splits, PA-level pitcher matching) could.

**2. A prior-season prior does not improve `batter-hit-v3`.** Shrinking a batter's early
rate toward *their own* prior-season rate instead of the league mean is **worse** at 20,
40, 60 and 150 observed PA — including, and especially, early in the season where it
should help most. The league mean alone (RMSE 0.03242) still beats the raw unshrunk rate
(0.04790) by a mile, which independently confirms v3's heavy shrinkage. **v3 is at the
ceiling this data supports.**

**3. Editorial signals cannot be calibrated against MLB outcomes — and this kills
`richer_game_outcomes` for MLB.** Tested out-of-sample on 5,173 games from 2020–2023 with
records reconstructed as of each game. The reconstruction is sound: favourite win rate
climbs monotonically with the record gap, 50.7% → 55.8% → 59.3% → 63.7%. But **margin does
not move**, and neither does anything else — close-after-7 sits at the 32.5% base rate for
every signal, lead changes at 1.38, comebacks at 8.0%. Correlations with min-win% are
+0.018 and −0.014.

Two consequences. The `even` rework earlier the same day showed a −0.55 margin effect
in-sample on 191 games; **it does not replicate.** That rework stands on its other
grounds — `marquee` firing on zero MLB games was a plain bug, and 16% card density beats
70% — but not on predicting closer games, and the decision log entry for it should be read
with this alongside. And `richer_game_outcomes` exists to replace margin with lead changes
and late closeness: both were tested here directly, both are flat. **Do not build it for
MLB.** The problem is not that margin is a crude proxy; it is that records predict *who
wins* and nothing about whether a game is worth watching.

**The one positive.** The same test on 5,838 NBA games behaves differently: mismatches
(gap ≥ .25) move all three measures the right way — margin 13.79 vs 12.54, close-after-Q3
26.6% vs 30.3%, comebacks 13.3% vs 16.8% — and `corr(gap, margin)` is +0.098 against MLB's
+0.031. **Competitiveness claims from records are defensible in basketball and not in
baseball.** Baseball editorial has to earn its value some other way.

**Cost.** About an hour, no production code. The third and fourth negative results in
three days, after `batter-hit-v4` and total bases, all reached by measuring before
building.

---

## 2026-08-10 — The vendor feeds contain odds; held, not read

**Decision.** The ingested box-score tables carry betting odds — `nba_team_games` has
opening/closing spread, total and moneyline plus line movements at **100% coverage across
six seasons**; CBB ~91%; MLB 2023 only. They are stored and **nothing reads them**.

**Reason.** They arrived as columns of feeds imported for other reasons. Stripping them
would have meant editing data on the way in, which is its own kind of dishonesty, and they
are genuinely useful for calibration.

**The tension, stated plainly.** A product rule says editorial signals use **no odds**,
enforced by an AST-based test. That test still passes and was not modified: it constrains
what code reads, not what a table holds. But "we ingest no odds" is no longer literally
true, and a future reader deserves to know that before they discover it.

**Why it matters now.** [Historical Data](HISTORICAL_DATA.md) §3 shows the editorial
engine cannot be calibrated against MLB outcomes at all. A closing line is the one
benchmark that plausibly could be — it is the market's own estimate of the same thing the
Game Interest score gestures at. That makes this worth deciding rather than leaving
implicit.

**Not a fix for `threshold_realignment`.** These are **game-level** lines, not player prop
lines. That item stays open.

**Options.** (a) Keep odds strictly held-not-read. (b) Allow them for backtesting and
calibration only, never in a user-facing surface. (c) Revisit the no-odds rule. **(b) is
the one worth discussing**; nothing should change without an explicit decision here.

---

## 2026-08-10 — Hold box-score history for sports the app cannot yet read

**Decision.** Ingest Big Data Ball box scores for **NBA, CBB, WNBA and MLB** into SQLite
via a new `src/boxscore_ingest.py` + `scripts/import_boxscore_feed.py`. 732,172 rows
across nine tables. **Nothing reads them.** No adapter, no scorer, no view.

**Reason.** The data existed but was unusable — spread across 143 near-duplicate
workbooks in iCloud, some 65MB, with no way to join one to another. NBA is
schedule-only in the app and CBB absent entirely, so none of it could inform anything.
Holding it in SQLite costs a table and makes it queryable the day a feature wants it;
leaving it in spreadsheets meant every future question started with an archaeology dig.
The explicit call was "bring them all to have if we need them; if they prove not useful
we can get rid of them later" — cheap to keep, expensive to re-derive.

| table | rows | seasons |
|---|---|---|
| `nba_player_games` | 197,807 | 2018–2021, 2023–2025 |
| `nba_team_games` | 14,496 | same, less 2023 |
| `nba_dnp` | 12,883 | 2024–2025 |
| `cbb_player_games` | 254,919 | 2024–2025 |
| `cbb_team_games` | 25,174 | 2024–2025 |
| `mlb_box_player_games` | 208,480 | 2020–2024 |
| `mlb_box_team_games` | 13,426 | 2020–2023 |
| `wnba_box_{player,team}_games` | 4,987 | 2020, 2025 |

**Why not reuse `nfl_ingest`.** Its field map renames a `1.0` column to `q1` — correct
for a football quarter, wrong for a **baseball inning**. Sharing it would have silently
mislabelled every MLB box score. The pure text helpers (`_clean`, `_dedupe`) are shared;
the semantics are not. Bare-numbered period columns now take a per-sport noun, because
the vendor emits `6` beside `1.0` and both mean the same kind of thing.

**Season calendars are explicit per sport.** NBA and CBB run autumn-to-spring, so a June
game belongs to the season that began the previous autumn; MLB and WNBA are simply the
year they are played in. Getting this backwards files every playoff game under the wrong
season. The rule survives the covid-shifted 2020-21 NBA season (December to July), which
is pinned by a test.

**The mistake worth recording.** Per-season replace assumed a newer pull is a fuller one.
It is not: the 2024-25 NBA feed (pulled 28 May, 1,312 games) overwrote the multi-season
archive's copy of that season (pulled 8 June, 1,339 games) and **deleted the Finals**.
Nothing errored. `import_feed` now refuses to shrink a season, reporting it instead, with
`--force` for the deliberate case. That class of loss is invisible until a query returns
a short answer months later.

**Honesty guards.** A feed with no game id — the 2020 WNBA vintage ships names only —
loads but is flagged `joinable: False`, because the project never joins on names and
stored rows must not look usable merely for having loaded. A sheet with no parseable date
is refused outright: a row we cannot place in time cannot be filed under a season.

**What the data actually contains** (checked, not assumed): the NBA archive spans 2018 to
2025 but holds **five** seasons, not seven — 2019-20 and 2022-23 are absent from it,
though a separate covid-shortened file fills 2019-20. 2022-23 is genuinely missing.

**Tradeoffs.** The DB grew 85MB → 252MB, all of it inert. Column sets are preserved
wide and unnormalised (58 columns for an NBA team game), which is deliberate — which stat
matters later is not knowable now — but it means these tables are not modelled, just
stored. No test asserts anything about their *content*, only about the reader.

**Future considerations.** The NBA team feed carries quarter-by-quarter linescores and
CBB carries halves: that is the shape `richer_game_outcomes` wants for "closeness entering
the final period", and it is now local rather than hypothetical. `nba_dnp` is the
availability signal whose absence caused the WNBA windowing bug. If a sport proves
useless, dropping its tables is one statement.

---

## 2026-08-10 — Editorial signals judged against their league, not a fixed number

**Decision.** `marquee` and `even` now test a team's strength **relative to its own
league** (`LeagueNorm.strength`) rather than an absolute win percentage, each paired
with an absolute floor. `even` additionally requires both sides to be good, not merely
similar. Card chips are passed the slate's norms, and `even` earns a chip only when a
norm exists. `services/editorial._both_clear`.

**Reason — the first fix the feedback loop paid for.** Measured over 191 finished MLB
games (base mean margin 3.39):

| rule | fires | mean margin |
|---|---|---|
| `even`, old (gap ≤ .100, min ≥ .400) | 134 | 3.45 *(vs 3.25 for everything else)* |
| gap ≤ .050 | 75 | 3.64 |
| normalised gap ≤ 0.5 SD | 49 | 4.06 |
| both sides at league strength ≥ 0.55 | 32 | 2.91 |

**Closeness of record predicts nothing, and tightening it makes things actively
worse.** The old rule fired on two-thirds of games — the base rate wearing a label —
and its games were *wider* than the rest. Quality does all the work: two **good** teams
play close games; two **similarly-rated** teams do not. "Evenly matched" was the wrong
concept, so the fix mirrors what `competitiveness` already does inside the score, where
closeness is weighted by quality.

`marquee` was worse than miscalibrated — it was **dead**. A raw `.650` is a bar no
baseball team reaches (the league tops out near .620), so it fired on **zero** of 191
MLB games and could not have appeared all season.

**Two bars, because each fails differently.** A relative bar alone crowns the least-poor
side on a slate of bad teams — caught by an existing test, where a 43-75 team was
labelled good because its peers were worse. An absolute bar alone does not travel
between sports. So `_both_clear` takes both, plus a conservative raw fallback used only
when the slate is too small to normalise.

**Result.** Both leagues now rank coherently — marquee < even < edge < solid <
struggling:

| signal | MLB n | margin | vs base |
|---|---|---|---|
| `marquee` | 9 | 2.11 | −1.28 |
| `even` | 31 | 2.84 | −0.55 |
| `edge` | 91 | 3.09 | −0.30 |
| `solid` | 44 | 3.41 | +0.02 |
| `struggling` | 47 | 4.19 | +0.80 |

**Chips.** `even` was previously barred from cards for a reason that was correct at the
time — a .100 gap covered half of baseball. That reason is gone, so it is now
card-worthy, but only where a norm exists: un-normalised, its fallback is an absolute
.500 bar that .508-vs-.517 clears while being the most ordinary pairing in the sport.
The game page can show such a read with its evidence; a chip has no room to qualify
itself. Chip density is now 16% of MLB cards and 15% of WNBA — MLB previously showed
**none**, since `marquee` was unreachable and `even` excluded.

**Tradeoffs.** Thresholds are tuned on 191 MLB and 40 WNBA games over two weeks, which
is thin — 0.55 and 0.65 are the best of a handful of candidates, not established
constants. Margin is a proxy for "worth watching" and always was. `solid` now measures
as uninformative (+0.02 MLB, +2.37 WNBA on n=9); it is kept because its job is to
*explain* the broad middle, not to predict, but it should not be trusted as a reason.

**Future considerations.** Re-check every threshold once `richer_game_outcomes` lands —
lead changes and closeness entering the final period are better targets than final
margin, and a signal tuned to margin may not survive them. Revisit `solid`'s place in
`_BEST_WORTHY`. Both `struggling` in WNBA (−3.36, n=7) and `solid` there look inverted
against MLB; more likely small-sample noise than a real cross-sport difference, but
worth a second look at n > 100.

---

## 2026-08-10 — A feedback loop for the editorial engine

**Decision.** Record how every finished game actually played out — final margin, total
score, winner, and the signals it carried — alongside the interest score it was given
beforehand. Runs with the daily rebuild (non-fatal), with a backfill script for
history. `services/game_outcomes.py` + `scripts/record_game_outcomes.py`.

**Reason.** Props are graded hit/miss nightly. A game's interest score was checked
against nothing, so the editorial engine was the one part of the product that could
not improve with data — more slates taught it nothing because no outcome was recorded.

**The leak, and why it matters more than the feature.** ESPN's record for a completed
game **includes that game**: the Yankees show 66-51 on a day they won and 66-52 the
next. Backfilling straight from that feeds the result into the input, and always in
the same direction, since the winner is the side credited. `pregame_record` rewinds
it. Without that the calibration would have flattered itself and we would have
believed it.

**What 232 backfilled games say.**

| | n | mean margin | close-game rate |
| --- | --- | --- | --- |
| MLB, interest ≥ 60 | 31 | **2.97** | **54.8%** |
| MLB, interest < 45 | 98 | 3.77 | 49.0% |

Real, and weak: **r = −0.111 within MLB**. Two things fall out of it —

- **Pooling leagues destroys the signal.** MLB alone is −0.111; pooled with WNBA it is
  −0.017. Margins are no more comparable across sports than win percentage was, so
  calibration is reported within a league.
- **The `even` signal does not do what it claims.** MLB mean margin by signal: `even`
  **3.45** (n=134), `solid` 3.19, `edge` 3.20. "Evenly matched" produces the *widest*
  margins — it is firing on nearly two-thirds of games and is essentially the base
  rate. That is the first concrete evidence that an editorial signal needs rework, and
  it exists only because this loop now exists.

**Tradeoffs.** Margin is a **proxy**, not truth: a 1-0 duel and a 12-10 slugfest are
both good games to different people, and no metric settles that. So the raw facts are
stored and no composite "watchability score" is invented. Lead changes and late-game
closeness are the obvious next measures, both derivable from data already held.

**Note.** Wiring this into the rebuild briefly broke the offline test guarantee — the
pipeline suite went from 3s to 37s making live calls. Faked in the fixture, with the
new step covered including its non-fatal failure path.

**Decision.** Do not add batter-vs-hand splits. Nothing shipped; this is the finding.

**Reason.** The effect does not survive honest regression on the data we hold.

| Stat | League vs L / vs R | Raw split p10/p90 | Shrunk (k=200) |
| --- | --- | --- | --- |
| Hit rate | .2075 / .2098 | −.043 / +.037 | **−.013 / +.011** |
| Strikeout rate | .2192 / .2113 | −.039 / +.048 | **−.013 / +.014** |
| Total bases/PA | .3364 / .3474 | −.105 / +.062 | −.027 / +.023 |

Two things make this conclusive rather than merely discouraging:

- **There is no league-level platoon effect in hit rate at all** (.2075 vs .2098), so
  any signal would have to be individual — and individual splits are thin. The median
  batter has **89 PA against left-handers** (p10: 29). At k=200, **0.0%** of batter×hand
  pairs show a shrunk delta above .04, against **21% raw**. The raw number is the trap.
- **A ±.013 shift in strikeout rate is 0.05 strikeouts across four plate appearances** —
  invisible against a 2+ threshold. It cannot move `batter_k`, the market it was most
  likely to help.

**The effect is real where the theory says it should be** — total bases, i.e. power, at
roughly twice the shrunk spread of the other two. That is the market retired the day
before for never clearing the curation floor. Platoon splits would have been the right
input for the wrong market.

**Scope of the claim.** This is measured on **season-to-date** data only. Career splits
carry several times the sample and might survive shrinkage; we do not have them, and
acquiring them is a data-source question rather than a modelling one. If multi-season
batter history ever lands, this is worth re-testing — the finding is "too thin here",
not "does not exist".

**Cost.** Fifteen minutes, no code. The second negative result in two days (after
`batter-hit-v4`), and both were reached by measuring the effect size before building
anything — which is the pattern worth keeping.

**Decision.** The Performance headline now leads with the **served** subset — props at
or above the curation floor, the ones a reader was actually shown — with the full
scored population underneath, labelled as including props that never cleared the bar.
`CURATION_FLOOR` moves to `services/grading.py` as the single definition, imported by
the Today view.

**Reason.** The ledger deliberately records the whole scored population, which is right
for calibration but wrong for a headline. Measured over the season to date:

| | Record | Rate | Graded |
| --- | --- | --- | --- |
| Served (70+) | 686–462 | **59.8%** | 1,148 |
| Whole scored population | 1642–1886 | **46.5%** | 3,528 |

A **13.2-point** gap, with **77% of rows never reaching a reader**. The dashboard's
main number was understating the product's actual advice by more than the entire
discrimination range of the batter-hit scorer.

**Tradeoffs.** Two numbers is more to read than one, and there is a real risk of
looking like the flattering figure was chosen. Mitigated by keeping both visible, in
one block, with the population's meaning spelled out rather than dropped — and by the
floor being one shared constant, so the served number cannot be quietly tuned by
changing a view.

**Note.** Retiring total bases and walks removed the two worst contributors to that
gap, so it should narrow going forward. The structural point stands regardless: any
market scoring below the floor distorts a population-level metric while never
reaching anyone.

**Decision.** Stop scoring `batter_bb`, following the retirement pattern set by total
bases the day before: the scorer half is deleted and the adapter method renamed
`k_bb_opportunities` → `k_opportunities`; the `MarketSpec` and grading branch **stay**
so the 70 graded rows still resolve and display.

**Reason.** Two arguments, and the second is the stronger.

- **It could never be recommended.** Exactly **one** walk prop has ever scored 75+, and
  none reached 85 or 90. Like total bases it sat permanently below the curation floor,
  scored and graded daily for a reader who never saw one. It converted 28.6% over 70
  graded rows.
- **The outcome is mostly the opponent's choice.** A walk depends more on how the
  pitcher attacks a hitter than on the hitter's own skill — which the app already
  conceded in its own risk line: *"Walks depend on plate discipline and how the pitcher
  attacks him."* No amount of accumulated data fixes a market whose result is largely
  decided by someone we are not modelling. This is why we did not wait for the sample
  to reach 100: more rows would have measured the same wrong thing more precisely.

**Tradeoffs.** Plate discipline is a real and under-covered attribute, and this was the
only market touching it. As with total bases, the loss is acceptable because the market
was not delivering it — but a genuine discipline market would need a bar that can reach
the floor, and probably an opposing-pitcher term, which we now know does not help the
hit market (see the v4 rejection).

**Watch next: `batter_k` has the same structural flaw.** Best score ever **69**, zero
props above 75 — also unservable. Its conversion is respectable (47.1%) and the sample
is small (34), so it is flagged rather than retired. If it stays unservable it should
follow, and the whole `src/batter_kbb_opportunity.py` module goes with it.

**The pattern is now explicit** in ARCHITECTURE: check a market can clear the curation
floor *before* building it. Three markets have now failed that test — home runs (caught
before shipping), total bases and walks (caught after).

## 2026-08-09 — Retire the batter-total-bases market

**Decision.** Stop scoring `batter_tb`. The scorer (`src/tb_opportunity.py`), the
adapter entry point, the cached builder and the slate wiring are removed. The
`MarketSpec` and the grading branch **stay**, so the 2,204 rows already in the ledger
continue to resolve, display and grade — history is never rewritten.

**Reason.** Four independent findings, any one of which would be enough:

- **It is strictly nested inside a market we already run.** You cannot record two
  total bases without a hit. Verified on 2,017 paired outcomes: **zero cases** where
  the TB prop hit and that player's 1+ Hit prop missed. Every TB win is a hit win,
  arrived at the hard way.
- **It cannot be recommended, by construction.** Best score ever achieved: v1 **67**,
  v2 **72**, v0.1 **64**. Exactly one prop in 1,124 reached 70; **none reached 75**.
  It sits permanently below the curation floor, so no reader has ever seen one.
- **It converts at 20.6%** over 1,124 graded rows — by far the worst market, and the
  v2 refit only lifted it to 28.2% on n=39, still nowhere near servable.
- **It distorts the headline metric.** It is 28% of the entire graded ledger and drags
  the population hit rate from 54.8% to **45.4%** — a 9.4-point penalty on the
  Performance dashboard's main number, paid for props nobody is shown.

**This is the same anti-pattern already rejected once.** The 2026-08-07 entry dropped
home runs as "the low-probability-over anti-pattern the TB/SP/WNBA refits removed."
Total bases is that pattern; it survived only because it was built earlier.

**Tradeoffs.** Extra-base power is a genuinely different attribute from contact, and
this gives up the only market that spoke to it. That is a real loss — but a market
that converts at 20% and can never surface was not delivering it. If power is worth
scoring, it needs a market designed for a reachable bar (as the WNBA and SP refits
were), not this one kept on life support.

**Future.** The ledger keeps its history, so the 9.4-point drag on the population rate
persists in past figures. That is correct — it happened — but it argues for the
Performance dashboard distinguishing **scored** from **served**, since a metric
dominated by props no one saw is not measuring what it claims to.

## 2026-08-09 — batter-hit-v4 (opposing starter in the score): TESTED AND REJECTED

**Decision.** Do **not** fold the opposing starter into the batter-hit score. The
evidence line stays (it informs a human reader); the score is unchanged and there is
no v4.

**The proposal.** log5 odds-ratio on the already-shrunk batter rate, with the pitcher
rate regressed toward league by batters faced (k=200), applied only to the starter's
share of expected PA (his own BF-per-start ÷ 9) with the remainder at baseline. Well
motivated: who is pitching is the largest input this market ignored.

**The result.** Backtested on **2,134 graded props across 9 slates**, recomputing both
the current scorer and the candidate from data strictly before each slate:

| | Q1 | Q2 | Q3 | Q4 | spread | corr | top-20% lift |
| --- | --- | --- | --- | --- | --- | --- | --- |
| current (v3) | 45.7% | 58.8% | 61.1% | **62.6%** | **+16.9%** | **+0.1124** | **+5.9%** |
| candidate (v4) | 47.7% | 56.6% | 61.2% | 62.7% | +15.1% | +0.1108 | +5.7% |

Worse on every measure. Not a dilution artefact: **94% of rows received an adjustment**
and the median pitcher sample was 429 BF. A variant without the bullpen split — the
full, undamped effect — was no better (spread +14.1%). At the top end, where served
picks live, it is a dead heat (top 10%: 65.4% vs 65.1%).

**Why the estimate was wrong, which is the part worth remembering.** The "10–14 points
of swing" figure that motivated this came from the **raw** pitcher spread (.167–.238,
0.80×–1.14× league). After applying the shrinkage the same proposal specified, the
realised spread is only **0.90×–1.10×** — then log5 compresses it further, then the
bullpen split compresses it again. The effect size was quoted from unshrunk rates while
the method used shrunk ones. Those are inconsistent, and the honest number is much
smaller than the one that justified the work.

**Tradeoffs.** A real effect can still fail to improve a ranking, because the noise it
adds can match the signal. Pitcher quality genuinely matters for whether a batter gets
a hit; it does not help us **order** batters, most of whom face pitchers within ±10% of
league once the estimate is honest.

**Kept:** `scripts/backtest_scoring.py`, the harness this produced. v2 and v3 were both
validated ad hoc with the code discarded; the next scoring proposal should not have to
rebuild it. Its rule is printed on every run: ship only if the candidate widens the
spread **and** lifts the top 20%.

**Future — better hypotheses than this one.** Platoon splits (batter vs LHP/RHP;
`pitcher_hand` is already in the feed and `team_vs_hand` uses it) are a sharper signal
than an aggregate rate. And the same mechanism is far more promising on **total bases**,
which grades at 19–28% and has much more room than a market already at 57%.

## 2026-08-09 — Reading two live boards prop-by-prop; six fixes and what it teaches

**Decision.** Audit the actual props for two games before first pitch — every line,
against the underlying data — rather than trusting the suite. Six defects surfaced,
two of them correctness bugs that **350 passing tests did not see**.

**Correctness.**
- **A traded player was offered for the team she had left.** Eligibility filtered
  *rows* by team, so a player who moved clubs kept her stale old-club rows and drew
  props in a game she was not in. Eligibility now follows the team of the most recent
  appearance; form still draws on every recent game, because form travels with a
  player and the club does not.
- **DNP rows silently shrank windows.** `head(5).dropna()` sliced before dropping, so
  five roster rows could collapse to one appearance still reported as "the last 5" —
  a single June game presented as a five-game sample. It also corrupted *threshold
  selection*, not just labels: one player's bar moved 10+ → 15+ once fixed.
- **Accented names lost every prop.** The schedule says "Randy Vásquez", the feed
  stores "Randy Vasquez"; exact matching returned `None` and that starter had no SP
  props at all — 2 of 30 probables on the slate. Matching now folds accents, and
  returns `None` on an ambiguous name rather than picking the first row.

**Evidence wording.** Severity now scales ("Ice cold — 1 hit in the last 25" replaced
"Recent hit rate has cooled" for a 1-for-25 batter); the WNBA gained a last-5 rule so
a player who cleared her bar twice in five no longer reads "No standout red flags";
stale start windows are named (a pitcher's "last 4 starts" spanning **128 days** now
says so, and stability drops 25); and every offered prop states its clear rate —
previously hidden on exactly the props sitting on the qualifying floor, 6 of 19.

**Added, not fixed:** the opposing starter now appears as evidence on batter-hit props.

**Reason.** The suite tested that the code did what it was written to do. None of it
asked whether the sentence beside the number was *true*, or whether the player was
even in the game. Those are only visible by reading real output against real data.

**Tradeoffs / what it teaches.**
- **A symptom fix can entrench a bug.** The first severity rule ("cleared none of the
  last 5") was written after seeing a 0/5 that only existed *because* of the DNP bug.
  Once that was fixed the branch became provably unreachable at every sample size and
  was removed. Fixing wording before checking the number made the app briefly more
  confidently wrong.
- **Numbers that don't reconcile are the signal.** The DNP and roster bugs were both
  found by chasing one figure — `average_l5: 12.0` against a player's actual last five
  of 25, 19, 20 — instead of moving on.
- Verifying against **live sources rather than fixtures** is what caught all six; the
  synthetic tests were written afterwards, from the real shapes.

## 2026-08-09 — OPEN: our prop thresholds sit far below where the question is asked

**Status: a finding, not yet a decision.** Recorded now because it reframes what the
Opportunity Score is for, and the answer changes the product.

**The finding.** Reading a live WNBA board against four real sportsbook lines showed
our bars land **1.5–3.5 below the market**, and that everything collapses at the line:

| Player | Our bar | Clears | Book line | Over rate (L10) |
| --- | --- | --- | --- | --- |
| Stokes rebounds | 4+ | **90%** | 6.5 | **50%** |
| Burton assists | 5+ | **80%** | 6.5 | **40%** |
| Hamby rebounds | 6+ | **70%** | 7.5 | **50%** |
| Burton points | 10+ | **70%** | 13.5 | **40%** |

Three separate causes:

1. **`MIN_CLEAR = 0.60` selects for reachability**, so a bar is chosen *because* the
   player clears it often — which by construction puts it below the median.
2. **The threshold grids cannot express a line.** Rebounds are `(4, 6, 8, 10)`,
   points `(10, 15, 20, 25)`; a 6.5 or 13.5 line has no representable neighbour.
3. **A priced line is an efficient estimate**, so any prop at one is ~50% — if it
   weren't, the book would move it. Our 90% exists precisely because nobody offers
   that bar.

**Why it matters.** The app is currently answering a question no one is asking, and
answering it accurately. The high-scoring props are the safest *and* the emptiest:
cushion and score move together, so value and correctness are inversely related by
design. A recommendation made from this board an hour before tip — "Stokes 4+ rebounds,
+50% cushion, 90% clear" — was true about our data and useless as advice, because at
the real line it is a coin flip.

**Useful corollary:** book lines tracked each player's own 10-game average to within
0.5–1.2 (Stokes 6.0 vs 6.5, Burton 6.2 vs 6.5, Hamby 7.6 vs 7.5, Burton 12.3 vs 13.5).
**A market-adjacent bar can therefore be approximated from our own data**, with no odds
ingested.

**The options.**

- **A — keep low bars.** Honest and high hit-rate; low relevance. Status quo.
- **B — median-centred bars, no odds.** Choose the threshold nearest the player's own
  recent median and add half-point granularity. Clear rates fall to ~50%, so the
  Opportunity Score can no longer mean "likely to hit" and must be redefined — e.g.
  how unusual the player's distribution is around that bar. Preserves "we ingest no
  odds"; the per-game distribution becomes the product.
- **C — ingest odds.** The only way to claim an *edge*, since edge is defined against
  a price. Reverses a core product decision stated three times in the Vision.

**Recommendation: B**, with the score redefined and the raw last-10 line shown
("Stokes: 7, 7, 11, 4, 4, 4, 7, 4, 3, 9"), which is more useful than any single number
and lets the reader hold it against whatever line they see.

**What this collides with.** The **2026-08-07 v2 refit** deliberately moved *toward*
reachable bars because impressive ones hit 17–44%. B is not a return to that failure
— those bars sat *above* the average, these sit *at* it — but it does undo the metric
that refit optimised, so the ledger comparison must be reset from the change forward.

**Untested hypothesis, logged so it isn't mistaken for a finding.** Three of the four
observed lines sat *above* the player's average, which would give unders systematic
value. n=4 and the four were hand-picked; needs real collection before it means
anything.

## 2026-08-09 — Competition context + editorial signals (curation without props)

**Decision.** Two connected pieces so a league with no player props is still curated.

- **Competition context** is six typed `SlateGame` fields — `season`, `phase`, `week`,
  `round_name`, `competition`, `neutral_site` — populated by all eight adapters, plus
  `conference_game` and team records/ranks. `phase` uses one vocabulary everywhere
  (`preseason`/`regular`/`postseason`), matching what `nfl_team_games.season_type`
  already stores, so a live game and an ingested one compare without translation.
- **`services/editorial.py`** turns records, ranks, conference and stakes into named
  signals, each carrying its evidence and caveats, plus a slate ranking and a
  `best_game()` that returns `None` when nothing deserves it.
- Shown in two places: a chip on the card (the slot the prop count would occupy) and
  a full **"The read"** section on schedule-only game pages, replacing the old
  "analysis is not connected yet" placeholder.

**Reason.** Football, hockey and basketball arrive with no props, so the slate showed
them as a bare fixture list. This answers "which of these is worth attention, and why"
from what the schedule honestly provides.

**Betting odds are deliberately excluded.** ESPN serves a DraftKings spread on every
event and it would be the strongest single signal available. The Vision lists odds
among what fans are already drowning in and says three times this is not a sportsbook;
the prop scorers already refuse them. A test fails if `odds` or `spread` appears in the
editorial logic, so reversing this is a product decision with an entry here, not a
quiet import. **Playoff leverage is also excluded** until the series/bracket model
exists — a guess dressed as leverage is worse than silence.

> **Supersedes** the 2026-08-07 decision that schedule-only cards render **compact**
> "since the reader only needs to know the game is on". That rationale was that there
> was nothing to say; where there now is, the card gets a footer chip. Cards with
> nothing notable stay compact, and a test covers both halves.

**Tradeoffs.** The honest limitation is that **win percentage is not comparable across
sports**. MLB's league sits inside roughly .380–.620 while a football team reaches
.900, so a fixed threshold means different things per sport, and poll ranks exist only
in college. Two consequences, both found by measuring real slates rather than
reasoning: "evenly matched" tagged **9 of 15 MLB cards** before being dropped from the
card chips, and a cross-league "best game of the day" is **not** shown at all, because
it would systematically pick football over baseball and call a metric artefact merit.
Chips therefore make a claim only about their own game. The engine also rewarded
closeness independently of quality until real data showed Sam Houston (1-8) at Oregon
St (2-8) scoring 45; competitiveness is now weighted by quality.

**Future.** Normalizing win percentage against each league's own spread would make a
cross-league best-game pick honest. `best_game()` exists and is tested but is not yet
surfaced anywhere for that reason.

> **Resolved the same day** — see *Cross-sport normalisation* below. `best_game()` is
> now honest; where (or whether) to surface it on the Today screen is still open, as
> that is a page-hierarchy decision rather than a correctness one.

## 2026-08-09 — Series position, and clinch/elimination without a bracket

**Decision.** Carry where a game sits in its series on `SlateGame` (`series_game`,
`series_total`, `series_summary`, and the leading/trailing tallies), from MLB
StatsAPI's `seriesStatus` — one hydrate, no extra calls. Derive **clinch and
elimination stakes** from the series shape alone: in a best-of-N, wins-needed is
`N // 2 + 1`, so a leader one short can clinch while the trailing side plays to
survive.

What is shown depends on the stakes, not the position: the postseason shows
"Elimination game" over "Game 6 of 7", and a level decider shows "Winner takes the
series" over "Series tied 1-1".

**Reason.** Baseball plays its regular season in series and every postseason is one,
so this is year-round context, not an October feature — all 15 MLB games on the day
this shipped were game 3 of 3. More importantly, **playoff leverage had been deferred
twice** (from `series_model` and from the editorial signals) on the assumption it
needed a bracket. Most of it does not; only seeds, slots and advancement wiring do.

**Tradeoffs.**
- `seriesStatus` describes the series **going into** a scheduled or live game and the
  finished result for a completed one. That was verified before building on it — the
  opposite convention would have leaked an outcome into a preview.
- The source words the standing as "WSH wins 3-0", which on a final card sits beside
  that game's own score and reads like one; anything not already saying "series" is
  labelled.
- The same 1-0 shape means different things in different months, so the regular
  season says "Series on the line" where the postseason says "Elimination game".
  Once a series is decided, stakes go silent — a dead rubber cannot eliminate anyone.

**Future.** Bracket structure proper — seeds, slots, TBD participants, advancement —
remains unbuilt and genuinely wants a live postseason to verify against.

## 2026-08-09 — Cross-sport normalisation: judge a team against its own league

**Decision.** Rank a mixed slate using each team's standing **within its own league**,
measured from the teams present on that slate (`LeagueNorm`), rather than raw win
percentage. A league needs **8 distinct teams** on the slate before its spread is
measured; below that it stays on raw win percentage and `cross_league_comparable()`
reports false so callers can withhold a cross-league claim.

**Reason.** Win percentage measures the sport as much as the team. Measured on a real
slate: MLB `sd = 0.062` against NFL `0.229` and NCAAF `0.242` — a 162-game season
pulls everyone toward .500 while a 17-game one lets teams reach .900. The consequence
was concrete: **every MLB game ranked below every WNBA game**, and MLB peaked at 57
where football reached 86. After normalising, Braves (71-47) at Yankees (66-52) tops
the slate at 77, which is the right answer.

**Tradeoffs.** The spread is measured from the slate, not hardcoded per sport — no
tuning, but it needs enough teams present, hence the gate. Within-league ordering is
provably unchanged (tested); only cross-sport comparison moves. **The signal
thresholds remain absolute** — `.650` for "marquee" — so a baseball game cannot earn
that label however dominant both sides are; normalising those too would change the
card-density calibration and was left for a deliberate pass.

**Future.** Surfacing a single "best game of the day" is now defensible; where it
belongs on the Today screen is an open hierarchy question.

## 2026-08-09 — `src/` is a leaf layer, enforced by a test

**Decision.** State the `src/` ↔ `services/` boundary as a **dependency direction** and
enforce it structurally.
- `src/` is a leaf library — external clients, ingestion, and the per-market scorers.
  It may import `domain/` (itself a pure leaf: stdlib only) and nothing else from the
  app. No Streamlit.
- `services/` sits above and imports `src/` freely.
- **`services/mls_store.py` moved to `src/mls_store.py`.** It imports only `sqlite3` —
  DDL and upserts, zero app knowledge. It was the sole reason `src/mls_collector.py`
  reached upward. Persistence belongs at the bottom of the layer diagram, not in
  `services/`; `services/migrations.ensure_schema` still calls its DDL, now importing
  downward. This also makes it consistent with `src/wnba_collector.py` and
  `src/nfl_ingest.py`, which already own their own persistence.
- `src/pitcher_opportunity.py`'s function-local `domain.markets` import was hoisted to
  module level — no cycle existed to justify hiding it.
- **`tests/test_layering.py`** parses every module's imports with `ast` (catching
  function-local ones, which a grep-based check misses) and fails on any upward import.

**Reason.** The boundary had been described as "historical" and was widely believed to
be fuzzy. It is not: it is a clean direction with, as of this change, zero violations.
An unwritten direction decays — principle 9 says prevent mistakes structurally rather
than relying on discipline, and that applies to the architecture's own rules. The guard
is written against *direction*, not a file list, so adding a module never requires
editing it.

**Tradeoffs.** One store now lives in `src/` while repositories and analytics stay in
`services/`, which reads slightly asymmetric until you know the rule — hence the
explicit paragraph in [Architecture](ARCHITECTURE.md#file-organization). The guard will
fail loudly on a legitimate future need to share code upward; the correct response is to
move the shared piece **down**, not to weaken the test.

**Future.** Two lower-priority couplings remain unaddressed and are *not* covered by the
guard: three `services/*_game_page.py` modules import `components.format.format_game_time`
(a pure formatter misfiled in the UI layer), and `components/` imports `services/` in two
places. Tightening principle 4 ("services should never contain UI") would mean moving
`format_game_time` into `domain/` or a formatting leaf, then extending the guard.

## 2026-08-09 — NFL archive holds many seasons (additive-per-season writes)

**Decision.** The NFL archive stores **multiple seasons**, not one.
- Ingest derives a `season` column from the game dates (Aug–Feb → that season) and
  writes **additively per season**: loading a new year replaces only that year and
  keeps the rest. The first run after this change migrates via one full replace, when
  the existing table predates the `season` column.
- The matchup builder scopes records, form, rest, and spotlights to **the game's own
  season**, so a Week 1 preview can't inherit last year's profile. `game_id` is
  globally unique, so lookups still need no season.
- The archive gains a season selector; `list_weeks` / `list_games` are season-aware.

**Reason.** A full-table replace on each import meant one season at a time — you could
not compare years, and re-importing to look at 2023 destroyed 2025. Season-scoped reads
are also the correct leakage bound: cross-season carryover is a subtler leak than a
date leak and would silently inflate early-week previews.
**Tradeoffs.** Season is *derived*, not read from the feed — a vendor file with
malformed dates would misfile games. The DB grows roughly linearly per season loaded.
**Future.** To add a past year, drop its Big Data Ball team + player workbooks and run
`python -m scripts.import_nfl_feed`. Cross-season views (franchise trends, year-over-year
identity) are now possible and unbuilt.

## 2026-08-08 — Batter 1+ hit v3: shrink the recent hit rate toward the league mean

**Decision.** `batter-hit-v3` shrinks a batter's recent per-PA hit rate toward the
league mean (0.25) by a factor of 0.70 **before** the `1-(1-p)^PA` estimate. Engine
version bumped; snapshots record it.

**Reason.** The accumulated v2 ledger confirmed the saturation flagged at v2: the
95–100 band hit only **40%** — *worse* than the 0–49 band (54%) — and picks piled up
tied at 100. The cause is statistical, not a bug: a 50-PA hit rate is a noisy talent
estimate, so hot streaks rocketed to the top and then regressed. Shrinkage is the
standard correction. Validated offline on the 287 graded v2 rows: the 85+ band recovers
from 52% (inverted) to ~62%, and picks at ≥ 99 fall from 6 to ~3. On a live slate,
tied-100s fell from 9 to 3 and the top 10 became a real gradient (100→93) instead of a wall.

**Tradeoffs.** **This does not manufacture signal.** 1+ hit is a hard ~55% event and
overall discrimination stays modest (corr ~0.07). v3 fixes a *misleading, inverted top*
— it does not make the market predictable, and a 100 must not be read as near-certainty.
The shrink constant is fitted to one ledger and will need refitting as data accrues.
**Future.** Re-check band calibration after another few hundred graded rows. If the top
band still fails to separate, the honest conclusion may be that 1+ hit does not deserve
its prominence, not that the scorer needs a fourth revision.

## 2026-08-08 — The NFL vertical: season-feed ingest → analytics → matchup page + props

**Decision.** Build the flagship NFL deep-dive (SPORT_PLANS tiers T1–T3) against
**ingested completed seasons**, reached through a **season archive** (`?view=nfl`), and
deliberately **not** wired to the live slate.
- `src/nfl_ingest.py` — Big Data Ball team + player workbooks → `nfl_team_games`,
  `nfl_player_games`, `nfl_teams`. A generic multi-row-header flattener handles both
  shapes (2 header rows / 3) and the repeated category fields.
- `services/nfl_repository.py` + `services/nfl_analytics.py` — leakage-safe reads, then
  a pure football engine. **A team's defense is derived by pairing** each game with the
  opponent's offensive row: points/yards allowed *are* the opponent's output. Season
  profiles carry league percentiles; `battlefields()` calls pass/rush O-vs-D edges.
- `src/nfl_opportunity.py` — props on the shared reachable-bar discipline
  (`src/reliability.highest_reachable_over`), by position, over-only.
- `services/nfl_game_page.py` + `components/nfl_game.py` + `views/nfl_archive.py` — a
  leakage-safe preview (identity, battlefields, form, a synthesized "read", rest) built
  only from games **before** kickoff, shown alongside the actual result.

**Reason.** A completed season is the *ideal* substrate for a deep matchup page: every
matchup exists, and because the outcome is known, each page is **its own backtest** —
player spotlights show the leakage-safe pick next to what the player actually did (✓/✗).
That is the fastest way to learn whether the analysis is any good before trusting it on
a live slate. Deriving defense by pairing avoids needing a second feed.

**Tradeoffs.**
- **NFL now has two disconnected surfaces**: a schedule-only live card and an
  archive-only deep-dive. They use different id spaces (ESPN event ids vs the feed's
  `AWAY@HOME` keys) and nothing reconciles them, so `views/game.py` does not dispatch
  NFL and `supports_deep_dive` stays `False`. This is honest but genuinely confusing to
  a reader of the code — hence the docstring there and [NFL Game Page](NFL_GAME_PAGE.md).
- NFL props are **not** registered in `domain/markets.py`: they are page spotlights
  only, so they are not snapshotted, graded, or counted in Performance.
- The preview leans on `yards_per_play` as its efficiency stand-in; there is no
  possession-adjusted metric, no EPA/DVOA, no injuries or weather.
- Percentiles need ≥ 2 teams, so tiny synthetic datasets fall back to raw comparisons.

**Future.** Reaching the live slate needs an ESPN↔vendor id bridge plus a weekly feed
cadence; then flip `supports_deep_dive` and add the dispatch branch. Registering the
props as `MarketSpec` entries would give NFL grading and Performance coverage for free.
T4 (playoffs/Super Bowl depth) is still open.

## 2026-08-07 — Batter strikeout + walk markets

**Decision.** Add two MLB batter markets — **batter_k** ("2+/3+ Strikeouts") and
**batter_bb** ("1+/2+ Walk") — on the shared reachable-bar discipline, feed, ledger,
grading, and lineup overlay. Both **over-only and distinctive by construction**:
- batter_k excludes "1+ K" (≈58% league-wide — not a signal) and offers no under (a
  contact hitter's "few Ks" overlaps the 1+ Hit market). ~16 high-whiff picks.
- batter_bb surfaces patient hitters. ~31 picks.
- Registry gains `prop_type_for(market_key, …)` so classification prefers the stored
  **market_key** — batter Ks and SP Ks both render "Strikeouts", so text alone would
  collide in the filter pills; text resolution is now a legacy-only fallback.
- **Home runs considered and dropped (not pursued).** 0 batters homer in ≥50% of
  games (best sluggers ~25–30%), so "1+ HR" could only ever be a ~25% longshot — the
  low-probability-over anti-pattern the TB/SP/WNBA refits removed. Out of scope.

**Reason.** The data decided which batter counting-stats fit: K and BB have
distinctive, reachable bars; HR does not. Both new markets sit mostly below the Today
curation floor, so they accrue graded data without crowding the shortlist.
**Tradeoffs.** batter_k is a small market (~16). Both are v1 (unvalidated) until
graded slates accrue — they join the same accumulate-then-assess plan.
**Future.** Reassess floors once graded; the duplicated reachable-bar logic (now in
tb / wnba / batter_kbb) is ripe for the shared selector.

## 2026-08-07 — Total-bases v2, WNBA grading fix, WNBA props v2

**Decision.**
- **Batter total-bases (`batter-tb-v2`).** Same failure as the SP overs: the
  impressiveness weighting chose the impressive bar over the reachable one — 83% of
  TB picks had a recent clear-rate < 0.35 and hit ~21% (4+ TB, the most-recommended,
  hit 20%). v2 offers a TB over only on the highest bar cleared in ≥50% of recent
  games and skips batters who clear none. Hold-out backtest next-game clear:
  17%→39%, volume 546→46 honest picks.
- **WNBA grading was silently broken (bug).** Box-score logs store `game_date` as a
  UTC timestamp (a night game rolls to the next UTC day), but grading matched the
  plain slate date → zero matches, so every WNBA prop sat pending/void and the
  learning loop was dead. Now matched by **(game_id, player_id)** (exact,
  timezone-proof), availability gated per game_id. Backfilled: 102 hit / 85 miss.
- **WNBA props (`wnba-pra-v2`).** With grading fixed, the scorer discriminates well
  (corr 0.39) but the mean-based anchor picked bars players clear <50% of the time
  (those hit 18–44%; rebounds worst at 40%). v2 offers a prop only on the highest bar
  cleared in ≥60% of the last 10. Hold-out next-game clear: points 37%→64%,
  rebounds 33%→68%, assists 32%→58%.

**Reason.** The fixed Performance/grading harness turned "the score feels off" into
measured, per-market clear-rate evidence — every refit here is validated against the
ledger or a leakage-safe hold-out before adoption, never hand-tuned.
**Tradeoffs.** All three refits trade volume for reliability (fewer, better picks) —
correct for over-only / low-base-rate markets, and the Today curation floor filters
further. Reliability floors (0.50 TB, 0.60 WNBA) are tuned to current data and may
need revisiting as more slates accrue.
**Future.** WNBA score top-end is still slightly noisy (80+ bands); revisit once more
graded slates exist. A shared "reachable-bar" selector could unify TB/SP/WNBA.

## 2026-08-07 — NFL schedule-only league + Today-screen curation/hierarchy

**Decision.**
- **NFL as a schedule-only league** (`leagues/nfl/adapter.py`, `src/nfl_api.py`,
  ESPN scoreboard), preseason included. It appears in the daily slate for
  awareness — no player analysis, no matchup deep-dive, no props. Same pattern as
  World Cup. Schedule-only cards (no analysis footer) now render **compact**
  (shorter), since the reader only needs to know the game is on.

  > **Superseded twice.** `src/nfl_api.py` was folded into the shared
  > `src/espn_scoreboard.py` + `leagues/_espn_schedule.ScheduleOnlyESPN` later the same
  > day. And "no deep-dive, no props" now holds only for the **live slate** — the
  > 2026-08-08 NFL vertical below builds both against ingested seasons, reached through
  > the archive. See [NFL Game Page](NFL_GAME_PAGE.md).
- **Top Opportunities is a curated shortlist, not a database.** The full slate
  shows only genuinely-strong picks (score ≥ `_CURATION_FLOOR` = 70, capped at 8),
  framed "Today's N strongest · curated from N scored" — not "914 opportunities".
  The whole scored population still feeds the ledger; this governs display only. A
  focused single game still lists every player.
- **Orange discipline on the opportunity screen.** Orange is reserved for the score
  (opportunity identity) and selection (active filters/threshold). The market label
  is now neutral, and secondary navigation is neutral until hover. Plus a hierarchy
  pass: lighter evidence-header/market weight, brighter team-metadata/evidence body,
  softer game-card borders, a shorter date control, and smaller prop-type pills.

**Reason.** With Scoring v2 the score finally spreads, so a hard curation floor is
now meaningful and "914 opportunities" read as dumping rather than curation. The
screen had also drifted toward a dashboard-y, orange-heavy, uniformly-bold look.
**Tradeoffs.** The curation floor (70) is tuned to the current v2 distribution
(~10% of props clear it) and will need revisiting if scoring changes materially.
NFL depends on ESPN's public endpoint (no fallback); an outage simply shows no NFL
games. Compact cards also apply to World Cup (consistent, intended).
**Future.** Batter total-bases is still v1 (unrefit), so it can dominate the
curated top until it's refit; segment-edge annotations on picks are the next lever.

## 2026-08-06 — Scoring v2: ledger-refit batter score + SP-over fix

**Decision.** Refit two scorers from the graded ledger (764 batter, 80 SP props),
validated offline before adoption, with per-market model versions bumped.
- **Batter (`batter-hit-v2`, `src/opportunity.py`).** Replace the hand-tuned
  weighted blend with the estimated 1+ hit chance `1-(1-p)^PA` (p = recent per-PA
  hit rate, PA = expected at-bats), rescaled to a spread 0–100 ranking signal with
  a small high-K penalty. The old blend spent 20/100 of its weight on last-25 hit
  rate — which the ledger shows is **noise** (corr ≈ 0) — and saturated near
  90–100, giving a flat calibration (~54–62% every band). Playing time
  (`pa_per_game`) was the strongest predictor (corr 0.14).
- **SP (`sp-v2`, `src/pitcher_opportunity.py`).** Penalize the **over** direction
  in `_best_direction` (×0.70 K, ×0.45 hits allowed). Recommended overs
  underperformed badly — hits-allowed overs hit 20% off a 60% recent clear rate
  (the stat is too variance-driven), K overs regressed to ~43% — while unders
  converted 57–61%.

**Reason.** The Performance dashboard surfaced that the score didn't discriminate
and that SP overs were unreliable. The fix had to be data-driven and measurable,
not another hand-tune. `component_values` stored per snapshot made the offline
refit/validation possible.
**Tradeoffs.** The batter score now spreads across 0–100 instead of clustering at
90–100 — a visible UX shift (fewer "90+" fire-lines). Still an **Opportunity
Score, not a probability** (rescaled and uncalibrated). The SP over-samples are
small (10/7); overs are penalized, not removed, so extreme cases still surface.
**Future.** New calibration (~52%→66% across bands) needs fresh `v2` slates to
confirm live. Follow-ups: segment-edge annotations on today's picks, a proven-edge
tier, shrunk segment priors, a post-hoc calibration map.

## 2026-08-06 — Results split into Daily Results + Performance (R1–R8)

**Decision.** Split the single Results view into **Daily Results** (`views/results.py`
— one slate, date nav, search/sort) and a **Performance** dashboard
(`views/performance.py`), over a shared query-param **filter bar**
(`components/filter_bar.py`) and shared grading definitions (`services/grading.py`).
Additive snapshot columns (`opponent`, `opposing_sp`, `start_time`, `void_reason`);
half-point over/under line reframe in the market registry ("1+ Hit" → "Over 0.5",
never a push); six finer score bands (75–79 … 99–100, MIN_SAMPLE=30); Altair charts;
**per-market** model versions (`MODEL_VERSIONS` in `services/snapshots.py`) replacing
the flat per-league string. Performance sections: period summary + comparison,
over-time trend, calibration, over-vs-under, edge finder by segment (team/opponent/
opposing-SP/player/month), consistency windows, by-month, model-version table.

**Reason.** One view couldn't answer both "what should I watch today?" and "is the
model any good over time?". Separating them let the second become a real evaluation
harness — which then drove Scoring v2.
**Tradeoffs.** More surface area; several additive columns and a filter-state
convention carried in the URL. Model-version comparison can't be reconstructed
retroactively (history keeps whatever it was stamped with) — honest only forward.
**Future.** Publication-time immutability (pin first capture per prop) deferred;
row-click drilldown on edge-finder segments deferred.

## 2026-08-06 — Batter Total Bases market + WNBA trend-depth parity

**Decision.** (1) Add an MLB **Total Bases** market as the first one built on the
registry: `src/tb_opportunity.py` scores "N+ Total Bases" from per-game `total_bases`,
choosing the threshold by impressiveness-weighted clear rate; a `batter_tb` MarketSpec
+ a "Total Bases" filter pill, wired into the feed/ledger/grading. The confirmed-lineup
overlay was extracted to `src/lineup_overlay.py` so Total Bases and 1+ Hit share the
slot-evidence + bench-cap logic (no duplication). (2) Bring **per-game trend depth** to
WNBA matchup pages (parity with the MLB batter spotlights): a points sparkline, a
double-figure (10+) dot row, L5/L10 windows, and a streak, computed from game logs.
**Reason.** Total Bases proves the registry's promise — a new market is "one MarketSpec
+ a scorer," with grading/classification/display automatic. WNBA trends were text-only
while MLB got the confidence-building depth; parity closes that gap on a live in-season
league.
**Tradeoffs.** Total Bases scores are honestly modest (it's a high-variance market), so
those props sit below 1+ Hit in the ranking and are found via the filter pill. The WNBA
dot row uses a fixed "double figures (10+ pts)" line rather than a per-player threshold —
recognizable and honest, but scoring-only (a rebound/assist trend still shows the points
trajectory).
**Future.** The remaining MLB markets (batter Ks, walks, HR) follow the same one-spec
recipe; WNBA depth could later key its dots to the player's actual points prop threshold.

## 2026-08-05 — Multi-device cloud access (durable DB store + in-app uploader + gate)

**Decision.** Make the app usable from phone/iPad/computer without the Mac on, by
deploying to Streamlit Community Cloud with the SQLite DB in a private S3-compatible
bucket. New pieces: `services/data_store.py` (fetch the DB from the bucket on boot,
publish after a rebuild; no-op locally), `services/settings.py` (secrets→env reader),
`services/auth.py` (optional password gate — required because the URL and uploader are
public), `services/update_pipeline.py` (one shared "import feed → refresh WNBA+MLS →
publish" used by both the CLI and the uploader), and `views/update_data.py`
(`?view=update`) — upload the day's Big Data Ball xlsx from any device and rebuild in
the cloud. Steps in [DEPLOY](DEPLOY.md).
**Reason.** The optimization target was multi-device ease *including updates*. The
bottleneck was never Streamlit — it was that the MLB data is a large, locally-sourced
feed and Community Cloud's disk is ephemeral. A private bucket + an in-app uploader
makes the data durable and the daily refresh device-independent, while the vendor feed
stays out of the public repo.
**Tradeoffs.** Cold starts (~30s wake); the in-app *cloud* rebuild may strain Community
Cloud's ~1 GB RAM (documented fallbacks: rebuild on the Mac and auto-publish, or host
on a small always-on box). Correctness never depends on the store — with no secrets set
the app behaves exactly as the local build (all cloud paths are opt-in). boto3 is a new
dependency but lazily imported (cloud-only). The final deploy step needs the owner's
Cloudflare + Streamlit accounts, so it is handed off via DEPLOY.md rather than automated.
**Future.** If cloud rebuilds prove too heavy, move hosting to Fly.io/Render; a
"refresh from bucket" button could replace the download-if-missing boot policy.

## 2026-08-05 — Structured market registry replaces market-text parsing

**Decision.** Make `domain/markets.py` the single source of truth for every prop
market. One `MarketSpec` per family (`batter_hit`, `sp_k`, `sp_hits`, `wnba_points`,
`wnba_rebounds`, `wnba_assists`) declares label noun, unit, source table, direction
rules, and prop-type, with behavior beside the data: `format_market` (canonical
label), `grade` (hit/miss comparison), `actual_display`, and `resolve` (legacy market
*text* → `(key, direction)`). `Opportunity` gains `market_key` + `direction`; scorers
already knew these (`pitcher_opportunity.kind`+dir, the WNBA stat key) and stop
discarding them at the adapter boundary. `opportunity_snapshots` gains additive
`market_key`/`direction` columns, backfilled once from legacy text via `resolve()`.
**Reason.** Grading, prop-type classification, and the results feed each parsed
market **text** (`"≤"`-prefix → under, substring → stat) in three separate places —
fragile, duplicated, and a blocker for adding NFL props. A registry centralizes the
rules and makes adding a market one `MarketSpec` entry.
**Tradeoffs.** The append-only ledger keys its PK on market text, so text stays the
stored display form; `market_key` is additive and `resolve()` keeps historical rows
gradeable. Labels are byte-identical to before (no visual change, no new PK values).
Verified: force-regrading 07-05 + 08-03 is identical; the only diffs were 08-02
`void→decided` from the data feed catching up, not the registry.
**Future.** Register NFL/NCAAF markets as new `MarketSpec` entries; the registry is
where a future structured void-rule / source-requirement per market would live.
Prerequisite for `nfl_props_volume` in the seasonal calendar.

## 2026-08-04 — MLB confirmed-lineup awareness in the batter hit scorer

**Decision.** Overlay **today's posted batting lineups** (MLB StatsAPI
`hydrate=lineups`, the same free source as the schedule) onto the 1+ Hit scorer via
`src/mlb_lineups.py` (fetch + `Lineups` model) and an optional `lineups=` parameter
on `score_hit_opportunities`. Three honest states: (a) **in a posted lineup** → a
"Batting Nth, confirmed lineup" support line + a small slot nudge (`_slot_bonus`,
±3); (b) **team posted but batter absent** → a "Not in today's posted lineup" risk
and the score **capped at 25** so a strong season can't float a benched player to
the top; (c) **not posted yet** → an honest "Lineup not yet posted", no penalty.
Joined by MLB player id (= the vendor feed's `batter_id`, verified 1:1; team names
also match the feed exactly). Cached in `app_cache.cached_lineups` (300 s TTL);
wired into both the slate feed (MLB adapter) and the MLB game page.
**Reason.** "Confirmed lineup context not yet included" was the caveat on nearly
every MLB card, and the single biggest quality gap was recommending a hitter who
turns out to be resting. Lineups are the highest-value new input, from a source we
already trust, and are leakage-safe (today's lineup for today's game; history stays
`as_of`-bounded).
**Tradeoffs.** Lineups post ~2–4 h before first pitch, so a morning open honestly
shows "not yet posted" for most games. A player traded mid-season can read as "not
in lineup" for his old club (harmless — he isn't a relevant pick there). The slot
nudge is deliberately tiny so recorded hit-rate history stays dominant.
**Future.** Projected lineups before official posting; expected plate appearances
from slot + pace; the same overlay for SP-vs-opposing-lineup quality.

## 2026-08-03 — Results Phase 2: score-threshold, market sub-filter, per-market rates

**Decision.** Make the Results view a learning instrument. It now loads the **full
scored population** and slices it three ways without changing what was stored:
score-threshold band pills (All / 75+ / 85+ / 90+ / 95+), a per-market sub-filter
(batter hits / SP K / SP hits allowed / points / rebounds / assists, namespaced so
it's independent of the Today feed), and a **"By market" hit-rate breakdown**
(`grading.summarize_by_market`). Market classification moved to `domain/markets.py`
as the single source of truth shared by the feed filters and the grading breakdown.
**Reason.** Phase 1 recorded and graded picks but showed them as one flat list;
"which markets convert, and does a higher score bar actually pay off?" was
unanswerable. Bands + per-market rates make the ledger legible.
**Tradeoffs.** Real signal needs accumulated graded days — a single slate is noise;
calibration *over time* (Phase 3) waits until the ledger has ~15–20 graded slates.
**Future.** Phase 3: hit rate by score band across dates, signal usefulness,
engine-version comparison.

## 2026-08-03 — Two-up card grid for the opportunity feed (density, evidence stays visible)

**Decision.** Replace the full-width opportunity row (a 4-column grid that stretched
evidence across wasted whitespace on wide screens) with a **two-up card grid** — 2
cards per row on wide, 1 on tablet, 1 with stacked evidence on phone — roughly
doubling props-per-screen. Both the "why it stands out" and "what could go wrong"
blocks stay on the surface. Scoped to `styles/app.css`; no logic changed.
**Reason.** The user asked to use space better. A considered alternative — moving the
red/green evidence into hover tooltips — was **rejected** because it violates the
non-negotiable rule that negative evidence stays at least as prominent as supporting
evidence, and tooltips break on touch. Density via layout keeps everything visible.
**Tradeoffs.** Uneven card heights within a row when one card's evidence wraps.
**Future.** Optional equal-height rows if the ragged bottom edge ever bothers.

## 2026-08-03 — MLB player trend spotlights (starting pitchers + high-conviction hitters)

**Decision.** Add per-player trend depth to the MLB matchup page (`services/mlb_trends.py`,
models in `domain/mlb_game_page.py`): a **Pitcher Trends** section (per-start K and
hits-allowed sparklines + direction + the SP props we serve + season K%), and an
**enriched Player Trends** section replacing plain Heating/Cooling — per-game 1+-hit
dot rows, L5/L10/L25 windows, current hit streak, and support/risk evidence. Leads
with **≥ 90-conviction** picks, then heating/cooling movers (`_build_spotlights`,
cap 6). All rendered with inline SVG (no charting library).
**Reason.** The user wanted to *feel more confident* about specific players —
especially starters and high-rated hitters. A score alone doesn't build conviction;
the trajectory behind it does, kept honest with visible windows and evidence.
**Tradeoffs.** More vertical space on the page (gated to real starters + movers).
**Future.** Bring the same per-game depth to WNBA player trends (currently text-only).

## 2026-08-03 — SP pitcher props (strikeouts + hits allowed), served two-directionally

**Decision.** Add starting-pitcher props — **SP strikeouts** and **SP hits allowed** —
scored in `src/pitcher_opportunity.py` from per-start lines (`services/mlb_pitcher_props.py`
builds them for the slate's probable starters), surfaced in the same Top Opportunities
feed, filterable by prop-type pills, and graded. Both markets are offered in **both
directions** (over *and* under), chosen by an **impressiveness-weighted** value
(rate × threshold-extremity) so a dominant strikeout pitcher surfaces a meaningful
"7+ K" rather than a trivial "≤ 8 K". Openers are excluded (`MIN_START_BF = 10`
batters faced) so they don't pollute the unders.
**Reason.** Batter 1+ Hit was the only market; pitcher props are the highest-value MLB
addition and the user watches them closely. A single fixed direction (e.g.
hits-allowed only as an under) misses the strong-over cases, so both are served.
**Tradeoffs.** `inning` is stored as `"1T"/"1B"` (parsed with a regex); starter
detection keys on a first-inning plate appearance. Thresholds are heuristic.
**Future.** More markets (total bases, batter Ks, walks, HR), each needing an honest
scorer + grader before it ships.

## 2026-08-02 — Prop grading + a dedicated Results view (Phase 1); DNP = void

**Decision.** Close the after-games loop. The Today view now records the **full
scored population** each day (not just a served top-N), and `services/grading.py`
grades each recorded prop **hit / miss / void** against stored results (MLB from
`plate_appearances`, WNBA from box scores), idempotently and only for dates strictly
before today. A player who **did not play** is **void**, not a miss — excluded from
the hit rate. A dedicated **Results** view (`?view=results`) shows a past slate's
graded props with a sport pill and a hit-rate summary. Grading columns
(`result`, `actual_value`, `graded_at`) were added additively to `opportunity_snapshots`.
**Reason.** Without grading, every day's reasoning was lost and the system could never
learn its own strengths and weaknesses. Recording the full population (per the user's
choice over an arbitrary threshold) is what makes later calibration honest. Counting a
scratch as a miss would understate the real hit rate — so voids are excluded.
**Tradeoffs.** The ledger only becomes informative as graded days accumulate; the
Results screen is deliberately read-only in Phase 1.
**Future.** Phase 2 (threshold + per-market breakdown — shipped 08-03) and Phase 3
(calibration over time). See [Roadmap → After Games](../product/ROADMAP.md).

## 2026-07-17 — MLS team-data integration + matchup analytics (Option A)

**Decision.** Collect **MLS regular-season team box-score statistics** from ESPN and
wire them into the matchup page, turning the Snapshot, Tactical Matchup, Attacking
Profile, Discipline, Storylines, and hero standings from honest placeholders into
**real, leakage-safe analysis**. New pieces: `src/espn_soccer` summary/standings
parsers; `src/mls_collector.py` (regular-season, completed-only, incremental,
validated, idempotent); additive tables via `services/mls_store.py`
(`mls_matches`, `mls_team_match_stats`, `mls_standings` snapshot-history,
`mls_collection_runs`); `services/mls_repository.py` (date-bounded reads);
`services/mls_analytics.py` (tactical proxies + storyline rules). Player stats
(Option B) and match events (Option C) were explicitly **out of scope**.
**Reason.** ESPN's MLS summary provides 28 team stats at ~100% coverage plus full
standings — enough to make the page genuinely useful with the smallest, most reliable
pipeline and the lowest delay risk. Player totals are too thin (no minutes/passing) to
power an honest Players-to-Watch, so they were deferred.
**Tradeoffs.** No player, event, lineup, or xG data yet (those sections stay honestly
unavailable). Accuracy percentages are **derived from raw counts** (the provider's
`*Pct` are lossily rounded); possession is provider-reported. Missing stats are stored
NULL, never zero. A local, gitignored SQLite backfill (191 matches / 30 clubs) must be
refreshed by running the collector — it is not part of the app runtime.
**Future.** Option C (match events) is the recommended next increment; Option B (player
data) waits on a richer source. See [MLS Game Page](MLS_GAME_PAGE.md) and
[MLS Provider Audit](../history/MLS_PHASE3A_PROVIDER_AUDIT.md).

## 2026-07-17 — Tactical honesty: measured proxies, one metric per section

**Decision.** The Tactical Matchup presents **honestly measured box-score proxies**
(Ball Share, Shot Volume, Shot Accuracy, Defensive Shot Pressure, Corner Pressure,
Crossing Volume, Passing Completion, Card & Foul Rate, Home/Away Performance) — never
"high press / low block / transition speed / width / directness / line height / game
control," which this data cannot support. A UX-refinement pass then gave **each
analytical section a single, non-overlapping metric set** (Snapshot = outcomes,
Tactical = style contrasts, Attacking = finishing/crossing, Discipline = fouls/cards),
suppressed low-signal rows, and added compact **similar-profile** states for even
matchups plus honest empty-storyline copy. Penalties are shown as a **per-match rate**
(not raw season totals); red cards remain event counts but state their sample size.
**Reason.** The first real-data render repeated the same metrics across sections and
produced walls of "Even" rows for similar clubs. Box-score stats are not tactical
identity; labeling them as such would violate the product's honesty rule.
**Tradeoffs.** For statistically even matchups the Tactical/Attacking/Discipline
sections may collapse to a single line rather than a table — deliberately calmer, and
scoped to style so it never contradicts a lopsided Snapshot. A banned-term test guards
the wording.
**Future.** When richer data lands (events, tracking), sections can add genuinely
tactical dimensions without relabeling the existing proxies.

## 2026-07-16 — MLS matchup page (soccer-designed, honesty-first shell)

**Decision.** Ship a dedicated MLS matchup page (`MLSAdapter.supports_deep_dive =
True`) as the reference implementation for soccer. It reuses the shared
architecture and design system and adds soccer-specific pieces (W/D/L form dots, a
nine-dimension tactical lean bar, a CSS/SVG formation pitch, a "what to watch"
timeline). The whole 11-section shell ships now; each section carries an explicit
`DataState` (Available / Partial / Projected / Unavailable) so the layout is fixed
while intelligence grows. Schedule is real via a new neutral ESPN soccer client
(`src/espn_soccer.py`, `usa.1`). The hero, a record/form snapshot, and a small
deterministic storyline engine run on **real** ESPN data (records, recent form,
colors, logos); everything requiring a soccer-stats pipeline renders as an honest
Unavailable/Projected state.
**Reason.** The philosophy is emphatic — *"Never invent statistics. Never fabricate
tactical conclusions."* — and there is no soccer stats pipeline yet. Building the
full shell with honest data states (rather than a fixture of fake numbers)
satisfies both "build the complete experience" and the non-negotiable honesty rule,
and lets real data drop in later with zero redesign. ESPN's MLS scoreboard already
returns real records, form, and colors, so the hero/snapshot/storylines are
genuinely substantive without fabrication.
**Tradeoffs.** Most analytical sections are Unavailable in V1 (tactical, lineups,
players, attacking, discipline) — the page is intentionally honest over full. Form
storylines rest on a 5-game sample (Low confidence; counted order-independently to
avoid a false directional claim). Reuses `mlb-*` section/storyline CSS for shared
primitives. A separate soccer client is kept from World Cup to avoid coupling
(national flags + bracket fallback vs. club logos + no fallback).
**Future.** Build the soccer data pipeline (collector + additive tables +
repository) per [MLS Phase 1 Inspection](../history/MLS_PHASE1_INSPECTION.md) §13; then flip
sections from Unavailable → real. `src/espn_soccer.py` is competition-agnostic and
can later absorb World Cup. See [MLS Game Page](MLS_GAME_PAGE.md).

## 2026-07-16 — WNBA matchup page (basketball-designed)

**Decision.** Ship a dedicated WNBA matchup page (`WNBAAdapter.supports_deep_dive
= True`) designed around basketball — Game Script, Snapshot, Team Identity,
"Where the Game Will Be Won" battlefields, Players Who Shape Tonight, Trending
Players, Team Trends sparklines, and the shared opportunity engine. It reuses the
MLB page's architecture and design-system primitives but has its own analytics.
**Reason.** WNBA had rich box-score data but only a schedule placeholder; the MLB
pattern transfers cleanly, and the spec asked for a basketball story, not a
baseball page with labels swapped.
**Tradeoffs.** Tempo uses an observed combined-scoring pace (not true possessions);
no injuries/lineups/advanced ratings yet (collected data doesn't exist). Reuses
`mlb-*` CSS class names for shared primitives (functional, slightly misnamed).
**Future.** `services/wnba_analytics.py` is basketball-generic — a future NBA page
reuses it. Advanced ratings / injuries / projected lineups plug in as new
collected data. See [WNBA Game Page](WNBA_GAME_PAGE.md).

## 2026-07-16 — Final-score V1 (scores on game cards)

**Decision.** Surface final and basic live scores on the game cards. Parsers now
extract `away_score`, `home_score`, a normalized `state` (pre/live/final),
`winner`, and `status_detail`; these are optional fields on `SlateGame` with safe
defaults. No schedule endpoint or hydrate parameter changed — the current
requests already return scores/state/winner for all three leagues. Kept the 120 s
cache TTL and the manual refresh; no live auto-rerun.
**Reason.** Scores are the highest-value live signal and were already in the raw
responses but discarded during normalization. Optional defaulted fields keep the
schedule cache backward-compatible (old rows deserialize with `None`).
**Tradeoffs.** Idle pages don't refresh until interaction/TTL; MLB inning and live
clocks are not shown yet.
**Future.** *Live State V2* (MLB `hydrate=linescore` inning/outs; WNBA quarter+clock;
soccer minute) and *Live Refresh V2* (auto-rerun only while a game is live) — see
[Roadmap → During Games](../product/ROADMAP.md).

## 2026-07-16 — Sport-specific game pages on shared product principles

**Decision.** Give each league its own game-page view (starting with MLB's
editorial preview) dispatched from the thin game router, rather than one generic
game page. The MLB page has its own navy "scorebook" visual identity but obeys the
same product rules (explainable, evidence-first, honest about missing data,
`as_of`-bounded) and reuses shared models (`Opportunity`, `DataStatus`) and the
existing opportunity scorer (same scores as the slate).
**Reason.** Different sports have genuinely different analytical stories; a generic
page can't tell them well. Isolating per-league rendering keeps the router thin and
lets leagues evolve independently.
**Tradeoffs.** More view/component/service code per league; some presentation
patterns (bars, stat rows) may later be worth generalizing.
**Future.** WNBA/World Cup get their own pages when data supports it; reusable MLB
patterns can be promoted into shared components. See
[MLB Game Page](MLB_GAME_PAGE.md).

## 2026-07-16 — Product name reconciled to "Sports Today" in the app

**Decision.** Rename the visible product name (window title, sidebar, in-app
messages, launch output) from "Sports Hub" to "Sports Today". Folders, modules,
tables, and internal identifiers were left unchanged.
**Reason.** The docs and product had standardized on "Sports Today"; the app UI
still read "Sports Hub". A narrow, user-facing rename removed the inconsistency
without churn.
**Tradeoffs.** Some internal docstrings still say "Sports Hub" (intentionally out
of scope); can be swept later.
**Future.** —

## 2026-07-15 — Documentation reorganized into a `docs/` knowledge base

**Decision.** Move all long-form docs out of the repo root into
`docs/{product,design,engineering,history}`, add a standard header
(Purpose/Audience/Update-when/Related) to each, cross-link them, and keep only
`README.md` and `CLAUDE.md` at the root.
**Reason.** The root had a dozen overlapping markdown files; discovery and
ownership were unclear. A curated hierarchy makes the repo feel like one product.
**Tradeoffs.** Internal links had to be updated; contributors must learn one new
map (mitigated by `docs/README.md`).
**Future.** Add `docs/` entries as new domains appear; keep history/ archival.

## 2026-07-15 — AI guidance stays a single `CLAUDE.md` (not split)

**Decision.** Keep one `CLAUDE.md` at the root as the AI entry point, pointing
into the product/design/engineering docs, rather than splitting into
`AI_PRODUCT_GUIDE` / `AI_ENGINEERING_GUIDE` / `AI_DESIGN_GUIDE`.
**Reason.** Claude Code auto-loads root `CLAUDE.md`; three files would duplicate
philosophy that already lives in the canonical docs. Splitting adds surface area
without improving clarity here.
**Tradeoffs.** `CLAUDE.md` must stay lean and defer to the docs instead of
restating them.
**Future.** Revisit only if AI guidance grows large enough that one file hurts.

## 2026-07-15 — Refine before redesign

**Decision.** Evolve successful layouts through typography, spacing, hierarchy,
and craft — not structural redesigns. Adopted after a redesign pass enlarged
components and added header metadata, then was reverted to the original layout.
**Reason.** A premium product is recognizable version to version; the redesign
increased vertical space and cognitive load without adding value.
**Tradeoffs.** Slower visual change; requires discipline to resist "big" redesigns.
**Future.** Any structural change needs an explicit reason logged here.

## 2026-07-15 — Product positioning: companion, not dashboard

**Decision.** Frame Sports Today as a calm daily companion that answers "what
matters today," explicitly not a stats dashboard, sportsbook, or fantasy tool.
**Reason.** A clear anti-positioning is the strongest feature filter we have.
**Tradeoffs.** We decline otherwise-reasonable features that don't serve the
daily moment.
**Future.** The decision filter in [Vision](../product/VISION.md) operationalizes
this.

## 2026-07-15 — Modular architecture with `views/`, not Streamlit `pages/`

**Decision.** Split the ~1,300-line `app.py` into `domain/`, `leagues/`,
`services/`, `components/`, `views/`, `router.py`, `styles/`. Do not use
Streamlit's automatic `pages/` directory.
**Reason.** One linear script mixed navigation, data, scoring, and HTML. `pages/`
would inject its own multipage nav that fights our same-tab query-param router.
**Tradeoffs.** A manual router is slightly more code than framework routing.
**Future.** New screens are plain modules under `views/`.

## 2026-07-15 — League adapters via Protocol + registry

**Decision.** Each league is a module implementing a `LeagueAdapter` Protocol and
registering an instance; the Today view consumes leagues only through the registry.
**Reason.** Adding a league should be "one adapter + one registry entry," with no
edits to shared screens. Protocols keep it lightweight vs. a class hierarchy.
**Tradeoffs.** Adapters must each satisfy the full contract, even schedule-only ones.
**Future.** NBA/NFL/NHL/etc. follow the same shape.

## 2026-07-15 — Normalized domain models

**Decision.** Introduce `SlateGame`, `Opportunity`, `Evidence`, `DataStatus`
dataclasses; adapters translate raw feeds into them so views render one shape.
**Reason.** Passing dicts around leaked league-specific shapes into every screen.
**Tradeoffs.** A translation layer per adapter.
**Future.** Extend models rather than reintroducing ad-hoc dicts.

## 2026-07-15 — Leakage-safe `as_of` enforcement

**Decision.** Every historical load is bounded by an `as_of` slate date; only data
strictly before it is returned.
**Reason.** Prevent future-data leakage *structurally* rather than by discipline —
essential for trustworthy scoring and honest retrospective evaluation.
**Tradeoffs.** Callers must thread `as_of` through data access and scoring.
**Future.** Any new scoring input must respect `as_of`.

## 2026-07-15 — Degraded-mode ordering (live → cached → labeled league-wide)

**Decision.** On schedule fetch: use live; on failure fall back to the most recent
valid cached slate; only then show an explicitly labeled league-wide fallback. A
legitimately empty slate shows no fallback.
**Reason.** A brief API hiccup must never change the meaning of the homepage, and
league-wide profiles must never masquerade as today-specific.
**Tradeoffs.** More states to handle and communicate.
**Future.** Same ordering applies to every future data source.

## 2026-07-15 — Cache strategy (SQLite + in-memory TTL), never load-bearing

**Decision.** Cache schedules in SQLite (cross-session, powers degraded mode) and
in-memory via Streamlit (120s) to avoid refetching on every rerun. Correctness
never depends on cache.
**Reason.** Performance and resilience without letting cache shape business logic.
**Tradeoffs.** Two cache layers to reason about.
**Future.** The app must remain correct with all caches cold.

## 2026-07-15 — Daily opportunity snapshots (seam + writes)

**Decision.** Persist each day's ranked opportunities with full context
(components, evidence, schedule provenance, `as_of` cutoff, context-availability
flags, engine version), idempotent per day. No review UI yet.
**Reason.** Without snapshots, every day's reasoning is lost; retrospective
evaluation would be impossible.
**Tradeoffs.** A new table and a write on the Today view.
**Future.** Build grading/evaluation on top (see Roadmap → After Games).

## 2026-07-15 — Single SQLite DB, additive tables + `schema_version`

**Decision.** Keep one `database/sportshub.db`; add new tables (`schedule_cache`,
`opportunity_snapshots`, `schema_version`) via a guarded, additive migration.
Existing tables are never touched.
**Reason.** A single-user local app doesn't need multiple databases; additive
migration keeps persistent data safe.
**Tradeoffs.** One file mixes raw, cached, and derived data.
**Future.** Split only if scale or concurrency demands it.

## 2026-07-15 — Project-scoped git repository

**Decision.** Initialize git inside the project folder; gitignore `.venv` and all
persistent data (`database/`, `data/`, `logs/`).
**Reason.** The enclosing home directory was an accidental repo; committing there
would sweep in unrelated files. Data artifacts don't belong in version control.
**Tradeoffs.** Data must be rebuilt on a fresh clone (documented in README).
**Future.** —
## 2026-08-16 — Grade every 70+ prediction; measure Featured separately

**Decision.** Every Opportunity Score >= 70 is a public qualifying prediction and is
graded. The top eight on Today are additionally stored as `featured` with ranks 1–8;
Performance exposes All qualifying, Featured, and Other qualifying cohorts.

**Reason.** Matchup pages publish the complete 70+ population, so all of it is valid
forward evidence and is needed to improve rating meaning over time. Featured answers a
different question: whether the cross-market ranking identifies a stronger shortlist.

**Tradeoffs.** Rows are correlated within a much smaller number of slates. The UI
therefore reports prediction and slate counts together, and scores remain ranking
signals rather than probabilities. Historical Featured membership is reconstructed
from stored pregame scores only; missing snapshots are never reconstructed.

**Future.** Add clustered uncertainty, precision@k, formal baselines, and market-specific
calibration before treating raw scores as comparable across markets. See
[`PREDICTION_EVALUATION.md`](PREDICTION_EVALUATION.md).
## 2026-08-17 — Live-state normalization and completed-game control

**Decision.** Normalize ESPN browser score states `pre` / `in` / `post` to the site's
pre / live / final vocabulary, replace scheduled time with the live/final badge, and
add a client-side Hide completed / Show completed control beside Hide games.

**Reason.** Scores were updating while active games retained their scheduled time
because ESPN calls the active state `in`, not `live`. Completed games also consumed
scarce phone space after their informational value had fallen.

**Tradeoffs.** Completed-game visibility is a temporary choice for the current page;
it intentionally resets after navigation. The published schedule remains the fallback
when browser score refresh is unavailable.
## 2026-08-17 — One-view market pulse uses within-market baselines

**Decision.** Add a combined Performance matrix with one row per active market and the
latest eight graded slates as columns. Cells show hit rate and sample, colored above /
near / below that market's own period average. Each row ends with its selected-period
rate and a latest-three-versus-prior-three-slate direction.

**Reason.** Separate diagnostic tables made it difficult to see whether market behavior
was improving, declining, volatile, or simply absent. A single view makes cross-market
patterns scannable without claiming that every market shares the same natural baseline.

**Tradeoffs.** Slate cells are descriptive, not independent confidence estimates.
Samples under five are faded, and direction requires at least ten decisions in both
three-slate windows; otherwise the UI says the sample is still building.
