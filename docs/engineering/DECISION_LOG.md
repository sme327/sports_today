# Decision Log

> **Purpose** — A living record of significant product and engineering decisions: what we decided, why, the tradeoffs, and what to revisit. Read this before proposing a change that reverses one of these.
> **Audience** — Engineers, product, design, and AI assistants.
> **Update when** — A significant decision is made or reversed. Append a new entry; don't rewrite history — supersede it.
> **Related** — [Architecture](ARCHITECTURE.md) · [Vision](../product/VISION.md) · [Design System](../design/DESIGN_SYSTEM.md) · [Docs index](../README.md)

Newest first. Each entry: **Decision · Reason · Tradeoffs · Future considerations.**

---

## 2026-08-09 — Retire the batter total-bases market

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
