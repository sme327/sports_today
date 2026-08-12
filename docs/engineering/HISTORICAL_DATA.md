# Historical Data — what we hold, what is missing, what it is good for

> **Purpose** — An inventory of the ingested box-score history, the specific gaps in it,
> and **measured** findings about whether it can improve the models. Read the last section
> before proposing work that depends on this data; several obvious ideas are already
> tested and dead.
> **Audience** — Engineers, product, and AI assistants.
> **Status** — Loaded 2026-08-10. Nothing in the app reads these tables yet.
> **Related** — [Decision Log](DECISION_LOG.md) · [Architecture](ARCHITECTURE.md) · [Sport Plans](../product/SPORT_PLANS.md)

Source files live in `~/Library/Mobile Documents/com~apple~CloudDocs/Sports Data/`, which
has its own README describing each workbook. Load with
`python -m scripts.import_boxscore_feed` (NBA/CBB/WNBA/MLB) or
`python -m scripts.import_nfl_feed` (NFL).

---

## 1. What we hold

Season labels follow each sport's own calendar: `2024` means **2024-25** for NBA/CBB/NFL
(autumn-to-spring) and the literal year for MLB/WNBA.

### NBA — `nba_team_games`, `nba_player_games`, `nba_dnp`

| season | team | player | DNP | note |
|---|---|---|---|---|
| 2018-19 | 1,305 | 1,305 | — | complete + playoffs |
| 2019-20 | 818 | 818 | — | **partial** — stops 2020-02-13, the covid shutdown |
| 2020-21 | 1,165 | 1,165 | — | complete; the shifted Dec–Jul calendar |
| 2021-22 | 1,322 | 1,320 | — | complete + playoffs |
| 2022-23 | — | — | — | **missing entirely** |
| 2023-24 | — | 1,317 | — | **team feed missing**, player present |
| 2024-25 | 1,316 | 1,339 | 1,256 | complete + Finals |
| 2025-26 | 1,322 | 1,322 | 1,232 | complete + Finals |

### CBB — `cbb_team_games`, `cbb_player_games`

| season | games | note |
|---|---|---|
| 2024-25 | 6,294 | full season through 2025-04-07 |
| 2025-26 | 6,293 | full season through 2026-04-02 |

Carries `conference`, `division` and `arena`, which no other sport's feed does.

### MLB box scores — `mlb_box_team_games`, `mlb_box_player_games`

Separate from the app's real MLB data (`plate_appearances`), which is play-by-play at
plate-appearance grain for the **current season only**. These are game-level box scores.

| season | team | player | note |
|---|---|---|---|
| 2020 | 951 | 951 | complete — the 60-game covid season |
| 2021 | 2,466 | 2,466 | complete + postseason |
| 2022 | 2,470 | 2,470 | complete + postseason |
| 2023 | 826 | 826 | **partial** — through 05-30 |
| 2024 | — | 381 | **partial** — through 04-25, team feed missing |
| 2025-26 | — | — | **missing** (current season is covered by the pbp feed) |

### WNBA box scores — `wnba_box_*`

| season | games | note |
|---|---|---|
| 2020 | 0 | **unjoinable** — this vintage ships no GAME-ID or PLAYER-ID, only names, and we never join on names. 1,806 rows stored but unusable |
| 2025 | 151 | **partial** — through 07-22 |

Distinct from `wnba_games` / `wnba_player_game_logs`, which the app's own ESPN collector
maintains and which the live product actually uses.

### NFL — `nfl_team_games`, `nfl_player_games`

| season | games | note |
|---|---|---|
| 2023 | 284 | through week 21 |
| 2024 | 282 | through week 20 |
| 2025 | 278 | through week 19 |

---

## 2. The gaps, in priority order

Nothing here is urgent — this is a shopping list for when it matters.

### High value if filled

1. **NBA 2022-23, both feeds.** The only fully absent NBA season in an otherwise
   continuous 2018–2025 run. Its absence breaks any year-over-year analysis spanning it.
2. **NBA 2023-24 team feed.** The player feed is present, so team-level context for a
   season we already have player data for is one file away.
3. **MLB 2023 and 2024 complete seasons.** Both stop in spring, which makes them useless
   for anything season-long. The full-season files exist from the vendor.
4. **Every NFL season's completed-postseason file.** All three stop a round or two short
   of the Super Bowl, because each was pulled in mid-January while that postseason was
   still being played. Re-pulling adds the missing rounds — no code required.

### Lower value

5. **NBA DNP for 2018–2023.** Only 2024-25 and 2025-26 have it. This is the availability
   signal whose absence caused a real windowing bug in WNBA scoring, so it matters more
   than its position here suggests — but only if an NBA feature is ever built.
6. **WNBA 2020 with IDs, or its removal.** As held, it cannot be joined to anything.
   Either re-source a vintage with GAME-IDs or drop the two tables' 2020 rows.
7. **WNBA 2021–2024.** Absent entirely; 2025 is partial.
8. **NFL 2018–2022 team feeds.** We hold a 2022 *player* feed that reaches the Super Bowl
   (the only such file in the collection) but no matching team feed, so it cannot be
   imported. 2018's team feed uses a pre-2019 layout the loader rejects outright.
9. ~~**MLB 2020–2022 odds.**~~ **Not a gap — they were there all along.** Those seasons
   pack the total and the favourite's moneyline into *one* column, split across the game's
   two rows, so the named columns read as empty. `services/mlb_odds.py` reconciles both
   vintages; all four seasons are usable (6,713 games with a total). See the 2026-08-11
   decision-log entry.

### Not gaps

- **MLB 2025-26** is covered by the daily play-by-play feed at finer grain. Do not
  backfill box scores for the current season.
- **CBB before 2024-25** — no reason to want it yet, since nothing reads CBB.

---

## 3. What the data is good for — measured, not assumed

Four questions were tested against this data on 2026-08-10. **Three came back negative.**
That is the point of testing them: each result removes planned work.

### ❌ Platoon splits are not a real batter trait — question closed

The [Decision Log](DECISION_LOG.md) rejected platoon splits as "too thin here, not does
not exist", flagging them to re-test **if multi-season batter history ever landed**. It
landed: 127,886 batter-games across 2020–2024 with the opposing starter's throwing hand.

With five seasons, the effect is now measurable where it was not before — at k=200
shrinkage, 5.5% of batters exceed a .040 split (was 0.0% on season-to-date data). But
measurable is not the same as real:

| test | result |
|---|---|
| split-half correlation of the **platoon split**, 2020-21 vs 2022-24 | **r = +0.077** |
| same split-half on **overall hit rate**, a known-real skill | r = +0.576 |

A batter's platoon split in one period barely predicts their split in the next. Overall
hit rate, measured identically on the same players, persists strongly. **The earlier
result was not a sample-size problem — the trait does not persist.** Do not revisit this
without a fundamentally better data source (career splits, or PA-level pitcher matching);
more seasons of the same will not change it.

### ❌ A prior-season prior does not improve batter-hit scoring

The scorer shrinks a batter's recent hit rate toward the **league mean** (v3 at the time
of this test; `batter-hit-v5` later cut the weight from 0.70 to 0.25). The obvious upgrade
is to shrink toward *that batter's* prior-season rate instead. Tested by
predicting the rest of a batter's season from their first N plate appearances:

| observed PA | n | shrink → league mean | shrink → prior season | change |
|---|---|---|---|---|
| 20 | 461 | 0.03008 | 0.03106 | **−3.3%** |
| 40 | 407 | 0.02995 | 0.03124 | **−4.3%** |
| 60 | 369 | 0.02957 | 0.03001 | −1.5% |
| 100 | 349 | 0.03066 | 0.03025 | +1.3% |
| 150 | 323 | 0.02999 | 0.03011 | −0.4% |

(RMSE, lower is better.) The prior-season prior is **worse** exactly where it should help
most — early in the season, when current-season data is thinnest. The one positive cell is
noise. Meanwhile the league mean *alone* (0.03242) beats the raw un-shrunk early-season
rate (0.04790) by a wide margin, which independently confirms v3's heavy-shrinkage design.

**Conclusion: v3 is already close to the ceiling this data supports.** The limitation is
not the prior; it is that a batter's hit rate is genuinely hard to predict.

### ❌ Editorial signals cannot be calibrated against MLB outcomes

The `even`/`marquee` rework of 2026-08-10 was tuned **in sample** on 191 MLB games, a
caveat recorded at the time. These box scores provide a genuine out-of-sample test:
5,173 MLB games from 2020–2023, with team records reconstructed as of each game.

The reconstruction is sound — it predicts winners cleanly:

| win% gap | n | favourite wins | mean margin |
|---|---|---|---|
| 0.00–0.05 | 1,362 | 50.7% | 3.554 |
| 0.05–0.10 | 1,291 | 55.8% | 3.435 |
| 0.10–0.20 | 1,727 | 59.3% | 3.463 |
| 0.20+ | 793 | 63.7% | 3.793 |

Favourite win rate climbs monotonically. **Mean margin does not move.** And no signal
separates from the base rate on any watchability measure:

| signal | n | margin | close after 7 | lead changes | comeback |
|---|---|---|---|---|---|
| *base rate* | 5,173 | 3.53 | 32.5% | 1.38 | 8.0% |
| both ≥.550 | 548 | 3.51 | 31.6% | 1.34 | 8.0% |
| close records (gap ≤.05) | 1,362 | 3.55 | 32.5% | 1.38 | 7.9% |
| quality **and** close | 472 | 3.51 | 32.0% | 1.33 | 8.9% |
| both <.450 | 408 | 3.51 | 29.4% | 1.37 | 7.8% |

Correlations of min-win% with close-after-7 (+0.018) and lead changes (−0.014) are zero.

**Two consequences.** First, the in-sample effects that motivated the `even` rework
(−0.55 runs) do not replicate; treat them as noise. The rework is still defensible on
other grounds — `marquee` fired on *zero* MLB games before it, which was a plain bug, and
firing on 16% of cards instead of 70% is better editorial regardless — but **not** on the
grounds that it predicts closer games.

Second, and more useful: **this kills `richer_game_outcomes` for MLB before it is built.**
That item exists to replace final margin with lead changes and late closeness. Both were
tested here directly. Both are flat. The problem is not that margin is a crude proxy; it
is that team records predict *who wins* and essentially nothing about *whether the game is
fun to watch*.

### ✅ In basketball, records do predict lopsidedness

The same test on 5,838 NBA games behaves differently:

| signal | n | margin | within 5 after Q3 | comeback |
|---|---|---|---|---|
| *base rate* | 5,838 | 12.54 | 30.3% | 16.8% |
| mismatch (gap ≥.25) | 1,550 | **13.79** | **26.6%** | **13.3%** |
| quality **and** close | 818 | 11.76 | 33.7% | 17.5% |
| both <.400 | 362 | 11.59 | 30.1% | 19.6% |

The mismatch row moves in the right direction on **all three independent measures**, and
`corr(gap, margin)` is +0.098 against MLB's +0.031. Better team wins 64.8% of the time,
against 56.8% in baseball.

This matches what the app already says about win percentage not being comparable across
sports — MLB's spread is far tighter. The practical reading: **editorial "how competitive
is this game" claims are defensible in basketball and football, and not in baseball.**
Baseball's editorial value has to come from something other than records.

---

## 4. The odds problem

**These feeds contain betting odds**, which nothing in the review process anticipated:

- `nba_team_games` — opening/closing spread, total and moneyline, plus line movements.
  **100% coverage, all six seasons.**
- `cbb_team_games` — same fields, ~91% coverage.
- `mlb_box_team_games` — **all four seasons**, once reconciled by `services/mlb_odds.py`:
  6,713 games with a total, 7,513 team-rows with a moneyline. 2020-22 price only the
  favourite; 2023 prices both sides.

This sits against an explicit product rule: editorial signals **use no odds**, a decision
enforced by an AST-based test. Holding odds in a table no code reads does not break that
test, and did not require changing it — but it is a real tension and should be a
deliberate choice, not a side effect of an import.

There is also an opportunity here worth naming, because a related item is open. The
`threshold_realignment` decision is OPEN partly because *"ESPN has no prop lines"*. These
are **game-level** lines (spread/total/moneyline), not player props, so they do **not**
resolve that item. What they would allow is calibrating the *editorial* Game Interest
score against a market — a much stronger benchmark than final margin, and one that
§3 suggests is the only thing that actually works in baseball.

**Decided 2026-08-11: option (b)** — offline for validation and benchmarking, never in a
surface. Evidence: both markets are efficient (every slice covers 0.48-0.53 against a
~52.4% break-even), so there is no edge to take; and the value showed up immediately when
the benchmark invalidated the NBA fatigue signal before anything was built on it.

**And it settles the MLB question.** `corr(line, |margin|)` is **+0.531 CBB / +0.195 NBA /
+0.047 MLB** — baseball closeness is barely predictable *even for the market*, so using the
line would not rescue MLB editorial. CBB is the sport where a line genuinely knows
something, and CBB has no surface.

---

## 4b. What the history *did* find (added 2026-08-10, later the same day)

Three findings the first pass missed, all validated:

- **Park factor is real in the history but does not transfer to the props.** Split-half
  r = +0.413 with a 12-point range on P(1+ hit) — yet across 2,714 graded `batter_hit`
  props, `corr(park factor, win)` is **+0.025** and the terciles are not monotonic.
  Backtested, not built. **Batter × park is noise** (r = +0.047). Home field is worth
  ~nothing on P(1+ hit): 0.5580 home vs 0.5601 road.
- **NBA fatigue predicts upsets — but the market already prices it.** Underdog at home
  with the favourite on a back-to-back: 42.9% against a 30.1% base, replicating across
  halves. Then measured against the **closing line**: B2B favourites cover 49.3%, within
  noise of 50%. Real, replicating, and **worth nothing** — the effect is entirely in the
  line. See the 2026-08-11 decision-log entry.
- **`sp_hits` carries no information; `sp_k` overs are the app's best signal.** Judged as
  lift over base rate rather than raw conversion. See the decision log entry for the
  three interacting decisions this raises.

Also checked and dismissed: batting order (86% of its huge raw spread is who bats there),
batter home/road (r = +0.127), batter-vs-pitcher (26 usable pairs in five seasons), and
porting the v5 weighting to WNBA (form beats volume there, the inverse of baseball).

**Superseding §3's "v3 is at its ceiling".** That conclusion held for the *inputs* tested
there (prior-season priors, platoon splits, park). It was wrong about the model: asking
which inputs the scorer *already has* actually predict the outcome produced
`batter-hit-v5` — recent form's weight cut 0.70 → 0.25 because plate appearances carry
more than twice its signal. Out of sample, test correlation +0.1127 → +0.1314 and top-20%
conversion 0.6419 → 0.6556. The ceiling was in the data we went looking for, not in the
data already in hand.

## 5. What is actually worth building

Ranked by evidence, not appeal:

1. **~~Resolve the three SP-scorer decisions~~ — done, 2026-08-10 (`sp-v3`).** Only one of
   the three was needed: threshold impressiveness now comes from measured rarity. Retiring
   `sp_hits` and un-penalising `sp_k` overs both turned out to be unnecessary once the
   cause was fixed — the `sp-v2` penalties move served lift by ~0.01 and were compensating
   for this distortion. Neither was touched.
2. **Nothing else from *new* inputs.** Three planned work items are dead (platoon splits,
   `richer_game_outcomes` for MLB, park factor as a `batter-hit` input). Park factor in
   particular is **rejected**, not pending — §4b has the backtest; an earlier draft of this
   section recommended it before that test existed.
4. **If an NBA feature is ever built**, the data supports it well — five seasons, quarter
   scores, DNP/availability, rest days, referee assignments, and full odds. NBA is also
   the sport where record-based editorial claims measurably work.
5. **Calibrate editorial against closing lines** (§4), if the odds question is settled in
   favour. This is the only tested route to making Game Interest mean something in MLB.
6. **Fill the gaps in §2** opportunistically — cheap, and they cost nothing to hold.

If none of this earns its keep, dropping the tables is one statement per table. That was
the agreed deal when they were loaded.
