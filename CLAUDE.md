# CLAUDE.md — Sports Today

Guidance for AI assistants (and humans) working in this repo. This file is
intentionally lean: it orients you and points into the knowledge base rather than
restating it. **Start with [`docs/README.md`](docs/README.md).**

> Naming note: the product is **Sports Today** — all user-facing surfaces (the
> window/page title, headers, launch output) say so. Some **internal identifiers**
> keep the original "Sports Hub" name by design (the `sportshub.db` filename, the
> `sports_hub_v1_daily` folder); that's intentional, not an inconsistency to fix.

## What this is

A personal **daily sports companion** — calm, explainable, curated. It answers
*"what should I pay attention to today?"* It is an analysis/opportunity tool, **not**
a sportsbook, dashboard, or fantasy platform. Today's slate carries **daily
opportunities** for MLB (batters: 1+ hit, strikeouts 2+/3+, walks 1+/2+;
SP strikeouts and SP hits allowed, both over/under) and WNBA
(points/rebounds/assists), with **matchup pages for MLB, WNBA, and MLS**. The
remaining leagues (World Cup, NHL, NBA, NCAA Football — via the shared
`src/espn_scoreboard.py` client) are **schedule-only**: no player props, but not
uncurated — `services/editorial.py` gives every game a team-level read (records,
ranks, stakes) shown as a card chip, and they have a **simplified matchup page**
(`web/simple_game.py`) carrying that read plus a plain statement of what a schedule
cannot show. It is offered **per game**: no link where the records are too young to
read, so a card stays compact when there is nothing to say.
Picks are recorded and graded daily (hit/miss/void) split
across a **Daily Results** view and a **Performance** dashboard — see
[Roadmap → After Games](docs/product/ROADMAP.md) and the
[Decision Log](docs/engineering/DECISION_LOG.md).

**NFL spans two surfaces, now joined.** Its deep-dive — season-feed ingest, team
analytics, player props, matchup pages — runs off ingested Big Data Ball seasons and is
browsed through the **season archive** (`?view=nfl`). The feed only ever contains
**played** games, so an upcoming game can never match `services/nfl_bridge.py`'s
date+teams join; a played, feed-covered game redirects to its archive page, and every
other NFL game gets a **pregame page** (`build_nfl_pregame_page`, since 2026-08-21)
built from aggregated data describing tonight's teams — this season's played games once
they exist, else the latest full season with the vintage named on the page ("12-5 in
2025"). No historical game ever stands in for today's (product rule, decision log
2026-08-21). NFL **does** score props onto the slate now (five over-only markets, since
2026-08-18), and goes quiet when the ingested feed is more than six weeks stale — which
is every preseason day. See [NFL Game Page](docs/engineering/NFL_GAME_PAGE.md).

**The NFL matchup effect is one-sided, and the page says so.** Measured over three ingested
seasons: a tough defence reliably suppresses passing (−15 to −22 yards) and, weakly,
rushing; **a soft defence does nothing** — every soft-side interval covers zero. Receivers
and usage are not moved at all (2 yards, 0.3 receptions). So `services/nfl_matchup.py` makes
**negative calls only**, has no `excel` state, and a test guards that no code path can
predict an above-baseline day. "He faces a bad defence, expect a big day" is the most common
claim in football previews and this data does not support it.

## Read before you build

- **Product** — [Vision](docs/product/VISION.md) · [Experience Principles](docs/product/EXPERIENCE_PRINCIPLES.md) · [Roadmap](docs/product/ROADMAP.md) · [Sport Plans](docs/product/SPORT_PLANS.md) (by-sport tiers + NFL deep-dive spec)
- **Design** — [Design System](docs/design/DESIGN_SYSTEM.md) (mirrors `styles/app.css`)
- **Engineering** — [Architecture](docs/engineering/ARCHITECTURE.md) (structure, "where to add X", glossary) · [Decision Log](docs/engineering/DECISION_LOG.md) · [Testing](docs/engineering/TESTING.md) · [Setup](docs/engineering/SETUP.md)
- **Method** — [Method](docs/engineering/METHOD.md) — **the tests that decide whether a signal is real.** Read before proposing any scoring or editorial change; most obvious-looking ideas here died to one of these checks.
- **Historical data** — [Historical Data](docs/engineering/HISTORICAL_DATA.md) (what we hold, the gaps, and what it measurably can't do) · [CBB](docs/engineering/CBB.md) (the most promising unbuilt sport, and why it stays team-level)
- **Per-league pages** — [MLB](docs/engineering/MLB_GAME_PAGE.md) · [WNBA](docs/engineering/WNBA_GAME_PAGE.md) · [MLS](docs/engineering/MLS_GAME_PAGE.md) · [NFL](docs/engineering/NFL_GAME_PAGE.md)

## How to contribute (the short version)

- **Refine before redesign.** Improve typography, spacing, hierarchy, and craft
  before changing structure. A change that adds cognitive load or vertical space
  without adding value is a regression. Check the
  [Experience Principles](docs/product/EXPERIENCE_PRINCIPLES.md) screen checklist.
- **Where to add code** — see the table in
  [Architecture](docs/engineering/ARCHITECTURE.md#where-things-live-quick-reference):
  new league → `leagues/<x>/adapter.py` + register; view → `web/`; component →
  `components/`; service → `services/`; domain object → `domain/models.py`;
  style → `styles/app.css`.
- **Don't reverse a logged decision** without reading its entry in the
  [Decision Log](docs/engineering/DECISION_LOG.md).
- **Prove it before you build it.** [Method](docs/engineering/METHOD.md) is the short list
  of checks — lift over base rate, split-half persistence, leakage, `√(2 ln k)`, and "would
  the market already know?". Roughly two thirds of this project's investigations are
  negative results, and they are the entries that saved the most time.

## Non-negotiable product rules

- **Explainable, always.** Every opportunity carries human-readable evidence.
- **Negative evidence is at least as prominent as supporting evidence.**
- **"Opportunity Score", never "probability"** (unless a calibrated model is
  explicitly built). Pair it with a **Stability Score**. Since 2026-08-21 the migrated
  markets (`batter-hit-v6`, `sp-v4`, `wnba-pra-v4`) share one scale
  (`src/score_scale.py`): 50 = no estimated edge over the market's own base rate,
  70 (the curation floor) = +10 points over it, 100 = +25. `batter_k`, `batter_bb`
  and NFL are deliberately not on it yet — see the module docstring before migrating.
- **Be honest about data.** Missing/stale/cached data is shown as such (degraded
  mode); never present it as fresh. The app may say there are no strong
  opportunities.
- **No forced quota by league.** Rank the whole slate on merit.
- **`as_of` everywhere.** Historical windows use only data strictly before the
  slate date — never leak future data.

## Coding standards

- Python 3.11+; prefer `pathlib.Path`; type-hint public functions.
- Keep ingestion, scoring, and UI rendering separate.
- Preserve MLB/game IDs; never join on names.
- Every score component must be inspectable; avoid opaque scores.
- Fail clearly on missing files/columns; don't silently invent baseball facts.
- Add/adjust tests when changing ingestion, result classification, or scoring.
- Don't hardcode absolute user paths; Downloads defaults to `Path.home()/"Downloads"`.

## Visual language (summary)

Dark, warm canvas; orange is the only accent (green = supporting evidence, coral =
risk, everything else grayscale). The hero title is white with only the possessive
word ("Today's") in orange. Layered surfaces over borders, soft shadows, subtle
motion. Full spec in the [Design System](docs/design/DESIGN_SYSTEM.md).

## Data & daily workflow

- The app reads `data/current/mlb_pbp_current.xlsx` and `database/sportshub.db`.
- Daily: drop the dated vendor feed in `~/Downloads`, run `update.command`
  (an alias of `update_and_publish.command` since 2026-08-20) — it archives,
  atomically replaces the current workbook, rebuilds SQLite, collects WNBA **and
  MLS** concurrently (both non-fatal on failure), precomputes the daily feed, and
  publishes the static site. It warns loudly when the newest feed is older than
  yesterday, and appends each run's summary to `logs/update_runs.jsonl`.
  `NO_CHANGE` is handled safely; data-only is `python -m scripts.morning_update`.
  The everyday entry point is **`Update Sports Today.app`** (Dock tile or Desktop
  alias, since 2026-08-27) — it opens a Terminal on `update.command`, resolves the
  project root from its own bundle so no user path is baked in, and refuses to start
  a second run while one is in flight (concurrent runs fight over the same SQLite
  database and the atomic workbook swap).
  Full steps: [Setup](docs/engineering/SETUP.md).
- **NFL feeds are picked up by the same daily run**, if a `*nfl-season-team-feed*.xlsx`
  + `*nfl-season-player-feed*.xlsx` pair is sitting in `~/Downloads`. Silent when there
  is none (most days, and all offseason), skipped when the pair is unchanged since the
  last import, and non-fatal on failure. In season this is what keeps the slate↔feed
  bridge working on *this* year's games. A one-off load is still
  `python -m scripts.import_nfl_feed`; writes are additive per season either way.

## Known limitations

- MLB is current-season only, at plate-appearance grain (no Statcast/exit velo/pitch
  type). NFL is the exception: it holds **multiple ingested seasons** (2023–2025).
- **Held-but-unused box scores.** `src/boxscore_ingest.py` has loaded NBA (2018–2025),
  CBB (2024–2025), MLB (2020–2024) and WNBA game logs — ~732k rows. **Nothing reads
  them**: no adapter, no scorer, no view, and the live slate for those leagues is
  unchanged. They are storage for future work, so don't infer from their presence that a
  league is supported. Load more with `scripts/import_boxscore_feed.py`. Coverage, gaps
  and **measured** findings: [Historical Data](docs/engineering/HISTORICAL_DATA.md) —
  read it before proposing work on this data; platoon splits and MLB
  `richer_game_outcomes` are already tested and dead.
- Season-to-date feed must be replaced daily; schedules need internet.
- MLB batter scoring now uses **today's confirmed lineups** when posted (from MLB
  StatsAPI): a confirmed slot adds evidence, a scratched batter is capped, and an
  un-posted lineup is shown honestly (never guessed). Batters who are not on the
  active roster are dropped entirely (StatsAPI roster status). The opposing starter
  appears as **evidence** ("allows hits 14% above league average") but is deliberately
  **not** in the score — folding it in was backtested as `batter-hit-v4` and rejected
  for making discrimination worse. Scoring still excludes weather, park and bullpen
  context. Do not represent scores as hit probabilities.
- **1+ hit is a hard event, and it is mostly about chances, not form.**
  `batter-hit-v5` shrinks the recent per-PA hit rate hard toward the league mean
  (`_HIT_SHRINK = 0.25`) because **plate appearances per game predict a hit more than
  twice as well as recent hitting does** (+0.130 vs +0.054 over 28k batter-games).
  (`batter-hit-v6`, 2026-08-21, keeps this estimate unchanged and remaps it onto the
  shared lift scale — same ordering, same served floor; the v5 findings below carry
  over. Two follow-ups were tested and rejected the same day: slot-implied expected PA
  loses the top — trailing volume partly *encodes* on-base talent — and the opposing
  starter re-tested on the v5 base closed most of its gap but still failed the ship
  gate. Both are in the decision log.)
  Overall discrimination is still modest by design — don't read a 100 as near-certainty.
  **Measured against its own base rate (2026-08-19), the market runs +1.5 on 1,337 served
  props** — close to no edge, and it is 61% of everything we serve. `batter-hit-v5` is
  nonetheless a real gain (+6.9, against +0.0 for its three predecessors pooled).
  **The top band is not broken under v5.** Pooled across all engines the 99-100 band reads
  −1.7, and that is *entirely* the retired scorers: `batter-hit-v5` alone runs **+13.4**
  there (n=27) and +20.3 at 95-98 (n=21). Both samples are far too small to celebrate —
  the point is only that the pooled negative is a version artifact, not a live defect, so
  don't "fix" the top of the scale on it. `v3_top_band_watch` remains open on sample size,
  not on evidence of inversion. Base rate for a starting
  batter is ~61%, not the ~55% quoted before — that older figure counted everyone who
  batted, pinch hitters included.
- **Compare a hit rate only against a base rate.** `services/base_rates.py` holds them;
  the Performance page ranks by lift. A shared average across markets is the one
  comparison the project treats as a bug — it reversed the true market ranking once.
- **Total bases was retired (2026-08-09)** and its `MarketSpec` kept only so old ledger
  rows still resolve. Don't re-add a scorer for it without reading the decision log: it
  is strictly nested inside 1+ Hit, converted 20.6%, and never once scored 75+ so it
  could never be recommended. **Batter walks looks like the same shape** — 1 prop ever
  above 75, and the outcome depends more on how the pitcher attacks than on the batter.
- **`sp_hits` is flat, not failing.** Measured 2026-08-19 with intervals: −4.1 ±6.2, not
  significant, so it is **not** a retirement candidate. The over side carries real signal
  (+14 to +19 at the top decile, out of sample) but 22 scorer variants all landed inside
  noise of the incumbent, so nothing shipped.
- **Judge a market on *all recorded props*, not the ones that cleared the floor.**
  Good-and-starved looks identical to bad until you separate them. The Performance page
  shows this directly (**Market coverage**), flagging a market as *Starved* when it beats
  its base by 5+ points yet under a tenth of its predictions ever clear the floor.
- **`batter_k` was the first thing that flag caught, and it is fixed** (`batter-k-v2`,
  2026-08-20). The reachable-bar filter did all the work (+14.0 pp on its own); after it
  the batter's own clear rate was noise (AUC 0.515), and because the 3+ bar is never
  reachable, `impressiveness = thr/max` was a **constant** that ranked nothing while
  capping the scale at 75 against a floor of 70. Rescaling that alone was tested and
  rejected (AUC 0.380 — worse than chance). **The opposing starter is what carries this
  market** (AUC 0.566): folding it in moved AUC 0.519→0.583, served props 4→85, and
  served lift to +25.3 over base. Not a reversal of `batter-hit-v4` — strikeouts are
  pitcher-driven in a way hits are not, and both were measured.
- **Editorial signals are records, not forecasts.** They use no odds (a deliberate
  product decision, enforced by a test), no injuries and no weather. A "Game Interest"
  score ranks a slate for attention — it is **not** a win probability and not
  comparable to a prop's Opportunity Score.
- **Win percentage isn't comparable across sports.** MLB's spread is ~4× tighter than
  football's, so cross-league ranking normalises each team against its own league and
  refuses the comparison when a league has too few teams on the slate.
