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
ranks, stakes) shown as a card chip and a "The read" section on the game page.
Picks are recorded and graded daily (hit/miss/void) split
across a **Daily Results** view and a **Performance** dashboard — see
[Roadmap → After Games](docs/product/ROADMAP.md) and the
[Decision Log](docs/engineering/DECISION_LOG.md).

**NFL is a separate surface.** Its live slate is schedule-only like the others, but a
full deep-dive — season-feed ingest, team analytics, player props, matchup pages —
runs off ingested Big Data Ball seasons and is browsed through the **season archive**
(`?view=nfl`), not the day's slate. The split is deliberate; see
[NFL Game Page](docs/engineering/NFL_GAME_PAGE.md) before changing it.

## Read before you build

- **Product** — [Vision](docs/product/VISION.md) · [Experience Principles](docs/product/EXPERIENCE_PRINCIPLES.md) · [Roadmap](docs/product/ROADMAP.md) · [Sport Plans](docs/product/SPORT_PLANS.md) (by-sport tiers + NFL deep-dive spec)
- **Design** — [Design System](docs/design/DESIGN_SYSTEM.md) (mirrors `styles/app.css`)
- **Engineering** — [Architecture](docs/engineering/ARCHITECTURE.md) (structure, "where to add X", glossary) · [Decision Log](docs/engineering/DECISION_LOG.md) · [Testing](docs/engineering/TESTING.md) · [Setup](docs/engineering/SETUP.md)
- **Historical data** — [Historical Data](docs/engineering/HISTORICAL_DATA.md) (what we hold, the gaps, and what it measurably can't do)
- **Per-league pages** — [MLB](docs/engineering/MLB_GAME_PAGE.md) · [WNBA](docs/engineering/WNBA_GAME_PAGE.md) · [MLS](docs/engineering/MLS_GAME_PAGE.md) · [NFL](docs/engineering/NFL_GAME_PAGE.md)

## How to contribute (the short version)

- **Refine before redesign.** Improve typography, spacing, hierarchy, and craft
  before changing structure. A change that adds cognitive load or vertical space
  without adding value is a regression. Check the
  [Experience Principles](docs/product/EXPERIENCE_PRINCIPLES.md) screen checklist.
- **Where to add code** — see the table in
  [Architecture](docs/engineering/ARCHITECTURE.md#where-things-live-quick-reference):
  new league → `leagues/<x>/adapter.py` + register; view → `views/`; component →
  `components/`; service → `services/`; domain object → `domain/models.py`;
  style → `styles/app.css`.
- **Don't reverse a logged decision** without reading its entry in the
  [Decision Log](docs/engineering/DECISION_LOG.md).

## Non-negotiable product rules

- **Explainable, always.** Every opportunity carries human-readable evidence.
- **Negative evidence is at least as prominent as supporting evidence.**
- **"Opportunity Score", never "probability"** (unless a calibrated model is
  explicitly built). Pair it with a **Stability Score**.
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
- Daily: drop the dated vendor feed in `~/Downloads`, run `update.command` — it
  archives, atomically replaces the current workbook, rebuilds SQLite, collects
  WNBA **and MLS** (both non-fatal on failure), and launches. `NO_CHANGE` is handled
  safely. Full steps: [Setup](docs/engineering/SETUP.md).
- **NFL is not part of the daily loop.** Its seasons are loaded one-off with
  `python -m scripts.import_nfl_feed` (team + player workbooks per season, written
  additively — a new year replaces only that year).

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
- **1+ hit is a hard ~55% event.** `batter-hit-v3` shrinks the recent per-PA hit rate
  toward the league mean to fix a saturated, *inverted* top band; overall
  discrimination is still modest by design. Don't read a 100 as near-certainty.
- **Total bases was retired (2026-08-09)** and its `MarketSpec` kept only so old ledger
  rows still resolve. Don't re-add a scorer for it without reading the decision log: it
  is strictly nested inside 1+ Hit, converted 20.6%, and never once scored 75+ so it
  could never be recommended. **Batter walks looks like the same shape** — 1 prop ever
  above 75, and the outcome depends more on how the pitcher attacks than on the batter.
- **Editorial signals are records, not forecasts.** They use no odds (a deliberate
  product decision, enforced by a test), no injuries and no weather. A "Game Interest"
  score ranks a slate for attention — it is **not** a win probability and not
  comparable to a prop's Opportunity Score.
- **Win percentage isn't comparable across sports.** MLB's spread is ~4× tighter than
  football's, so cross-league ranking normalises each team against its own league and
  refuses the comparison when a league has too few teams on the slate.
