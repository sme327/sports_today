# Architecture

> **Purpose** — How the codebase is organized and the principles that keep it maintainable as leagues and features grow.
> **Audience** — Engineers and AI assistants writing code.
> **Update when** — A structural pattern, layer boundary, or naming convention changes. Log the decision in [DECISION_LOG](DECISION_LOG.md).
> **Related** — [Decision Log](DECISION_LOG.md) · [Testing](TESTING.md) · [Setup](SETUP.md) · [Vision](../product/VISION.md) · [Docs index](../README.md)

---

## Where things live (quick reference)

| To add… | Put it in… |
| --- | --- |
| a new **league** | `leagues/<name>/adapter.py` implementing `LeagueAdapter`, then `register(...)` and import it in `leagues/__init__.py`. **Schedule-only + ESPN-covered?** subclass `leagues/_espn_schedule.ScheduleOnlyESPN` (set `espn_path`, emoji/label) — ~8 lines; the shared `src/espn_scoreboard.py` does fetch/parse |
| a new **screen/view** | `views/<name>.py`, dispatched from `router.py` |
| a new **component** (reusable UI/HTML) | `components/<name>.py` |
| a new **service** (data, schedules, cache, snapshots, migrations, repository, analytics) | `services/<name>.py` |
| a new **domain object** | `domain/models.py`, or a league page model (`domain/<league>_game_page.py`) |
| to **change a scorer** | edit the scorer **and** its `services/snapshots.MODEL_VERSIONS` string in the same commit — a test ties each version to a property of the engine it names, because a mislabelled slate silently credits a new engine's results to the old one |
| a new **prop market** | a `MarketSpec` entry in `domain/markets.py` (label, unit, direction, grade rule, source) + a scorer in `src/`; grading/classification/display then work automatically. **Before adding one, check it can actually clear the curation floor** — total bases never scored above 72 in 1,199 graded rows, so it was scored daily for a reader who never saw it |
| to **retire** a prop market | delete the scorer, adapter entry point, cached builder and slate wiring; **keep** the `MarketSpec` and grading branch so existing ledger rows still resolve. Never delete graded history |
| **grading / Results & Performance** logic | `services/grading.py` (grade + summarize by band/segment), `views/results.py` (Daily Results), `views/performance.py` (Performance dashboard), `components/results_feed.py`, `components/filter_bar.py` (shared query-param filter bar) |
| a new **sport's player game logs from ESPN** | add a `SportSpec` to `src/espn_boxscore.SPORTS` (ESPN path, table prefix, stat aliases, columns, plus `groups`/`limit` for college sports) and collect with `scripts/collect_espn_boxscores.py`. Validate against a second source where one exists, and against the sport's own real-world rates where it does not |
| a new **data collector** (fetch → normalize → SQLite) | `src/<league>_collector.py`, writing via a `src/<league>_store.py` (DDL + upserts; keep it a leaf so the collector stays runnable headless) |
| a new **vendor season-feed ingest** (workbook → SQLite) | `src/<league>_ingest.py` + a `scripts/import_<league>_feed.py` CLI. Write **additively per season** so loading a new year keeps the others, and declare a **required-column contract** so vendor layout drift fails at import instead of producing a table that quietly breaks a page later (see `src/nfl_ingest.py`) |
| **automatic pickup** of a dropped vendor feed during the daily run | a `services/<league>_feed_refresh.py` called from `services/update_pipeline.rebuild()` inside its own `try`. Search **`~/Downloads` only** — an automated job must not walk a personal documents tree — and make it idempotent by source-file fingerprint so a 9MB workbook is not re-parsed daily (see `services/nfl_feed_refresh.py`) |
| a new **sport's box scores** (game logs held for later, not yet surfaced) | `src/boxscore_ingest.py` — add a `Sport` to `SPORTS` (season calendar + period noun + table prefix) and import via `scripts/import_boxscore_feed.py`. Handles both vendor header shapes. **Nothing reads these tables**; they are storage until a feature needs them |
| to **interpret an awkward vendor encoding** (packed columns, vintage drift) | a `services/<x>_odds.py`-style reader that **interprets without rewriting** the ingested table — `src/` stays faithful to the source, `services/` decides what it means. Validate the interpretation against outcomes (see `services/mlb_odds.py`, whose favourite-attribution is confirmed by a 59.5% win rate) |
| to **join a live schedule game to ingested vendor data** | a `services/<league>_bridge.py` matching on date + teams (never on ids, which differ by source), returning `None` freely; then a per-game `deep_dive_available(game)` on the adapter so cards only link where a page exists (see `services/nfl_bridge.py`) |
| a new **archive browser** (browse ingested history, not today's slate) | `views/<league>_archive.py` + a `view` value in `router.py` and a dispatch branch in `app.py` (see `?view=nfl`) |
| a new **editorial signal** (team-level curation, no player props needed) | a rule in `services/editorial.py` returning a `Signal` with its evidence **and** caveats; add it to `_CARD_WORTHY` only if it belongs on a card. Rendering is `components/editorial.py` |
| **competition context** for a league (season, phase, week, round, series) | populate the typed `SlateGame` fields in that league's adapter; `notable_context` decides what is worth showing |
| a **research table** (held for later, not read by the app) | add it wherever it belongs, and **do not** add it to `scripts/build_deploy_db.KEEP` — the deploy build is an allow-list, so it is excluded by default and never ships to a phone |
| a **schema table** | add DDL to the store module and call it from `services/migrations.ensure_schema` |
| a **style/token** | `styles/app.css` (one stylesheet) |
| a **test** | `tests/test_<area>.py` (offline; no network) |

Ingestion and lower-level data collection live in `src/` (kept from the original
build). A league that collects its own history follows the collector pattern
(`src/wnba_collector.py`, `src/mls_collector.py`): a **collector** orchestrates
fetch/retry/incremental/audit, a neutral **client** does transport + pure parsing
(`src/espn_soccer.py`), a **store** owns DDL + upserts (`src/mls_store.py`), a
**repository** does leakage-safe reads (`services/mls_repository.py`), and an
**analytics** module does deterministic computation (`services/mls_analytics.py`).
Everything else follows the layers below.

## Glossary (canonical terminology)

- **View** — a screen module in `views/` (Today, Game). We deliberately do **not**
  use Streamlit's automatic `pages/`. Say "view", not "page", for code.
- **Component** — a reusable rendering helper in `components/`. Not "widget".
- **Service** — an operation module in `services/` (data access, schedules,
  cache, snapshots, migrations). Not "manager".
- **Adapter** — a league implementation of the `LeagueAdapter` protocol.
- **Domain model** — a normalized dataclass in `domain/models.py`
  (`SlateGame`, `Opportunity`, `Evidence`, `DataStatus`).
- **Opportunity Score** — the primary, transparent, inspectable score. **Not a
  probability.** Paired with a **Stability Score**.
- **Slate** — the set of games for a given date.
- **as_of** — the slate date that bounds every historical window; only data
  strictly before it is used (prevents leakage).
- **Degraded mode** — live → cached → labeled league-wide fallback ordering.
- **Snapshot** — a persisted daily record of the ranked opportunities and their
  context. The **full scored population** is recorded (not just a served top-N).
- **Grading** — scoring each recorded prop **hit / miss / void** against actual
  results; a player who did not play is **void** (excluded from the hit rate), never
  a miss. Lives in `services/grading.py`; surfaced in the **Results** view.
- **Prop market** — a market a prop is scored in (batter 1+ hit / strikeouts / walks,
  SP strikeouts, SP hits allowed, WNBA points/rebounds/assists). A **retired** market
  keeps its `MarketSpec` so old ledger rows still resolve, but has no scorer — see
  `batter_tb`. `domain/markets.py` is the **registry**
  (one `MarketSpec` per family) and the single source of truth for a market's label,
  unit, direction, grade rule, source, and prop-type — used by the scorers, grading,
  the feed filters, and the Results breakdown. Legacy snapshot rows (which store market
  *text*) are re-classified by `resolve()`.
- **market_key / direction** — the structured identity of a prop (registry key +
  over/under), stored on `Opportunity` and each snapshot so grading never re-parses
  label text.
- **Competition context** — where a game sits in its competition: season, **phase**
  (`preseason`/`regular`/`postseason` — one vocabulary shared with the ingested NFL
  feed), week, round, competition, neutral site, and series position. Typed fields on
  `SlateGame`; unknown stays `None` and is omitted rather than guessed.
- **Editorial signal** — a team-level observation (`marquee`, `upset_setup`,
  `ranked_pair`, …) for leagues with no player props, each carrying its evidence and
  caveats. Lives in `services/editorial.py`.
- **Game Interest score** — ranks a slate for **attention**. Not a probability, and
  deliberately unrelated to a prop's Opportunity Score. Only comparable across
  leagues after `LeagueNorm` normalisation, because win percentage means different
  things in different sports.

---

## Purpose

Architecture exists to make the product easier to evolve. Not to impress engineers.
Not to maximize abstraction. Not to demonstrate design patterns.

Every architectural decision should answer one question:

> **Will this make Sports Today easier to improve next year?**

## The Prime Directive

Every feature should be easy to understand. If a new engineer cannot locate where a
feature lives within a few minutes, the architecture has failed.

## Guiding Principles

### 1. Organize around the product

Code should reflect how users think. Not how frameworks think.

Good:

```
Today
Tomorrow
Game
Player
League
Opportunity
```

Less good:

```
helpers
utils
misc
common
functions
services2
```

The folder structure should mirror the product.

### 2. Domains own behavior

A Player should know what a Player is. A Game should know what a Game is. An
Opportunity should know what an Opportunity is.

Avoid passing dictionaries through the application. Favor meaningful domain models.

### 3. Views are dumb

Views render information. Views do not perform business logic.

Views should answer: "What should be displayed?" Never: "How should opportunities be
calculated?"

### 4. Services do work

Services perform operations. Examples: schedule loading, database access, snapshot
writing, caching, migrations, external APIs.

Services should never contain UI.

### 5. Adapters isolate leagues

Every league should implement the same contract. The rest of the application should not
care whether the data comes from MLB, NBA, NFL, WNBA, World Cup, or something not yet
imagined.

Adding a new league should require:

- one adapter
- one registry entry

Nothing else.

### 6. Prefer composition over inheritance

Small focused objects. Small focused functions. Compose behavior. Avoid deep
inheritance trees.

### 7. Avoid global state

Global state becomes hidden coupling. Pass dependencies explicitly. Cache
intentionally. Never rely on magic.

### 8. Explicit beats implicit

Good: `as_of`, `league`, `game_date`, `mode`.

Bad: `current`, `active`, `latest`, `selected`.

Variables should explain themselves.

### 9. Make invalid states difficult

Architecture should prevent mistakes. Example: a scoring engine should not be capable
of accidentally loading future games.

Prevent leakage structurally. Do not rely on discipline.

## Product Layers

The application should naturally separate into layers.

```
User
↓
View
↓
Router
↓
League Adapter
↓
Scoring Engine
↓
Evidence Builder
↓
Domain Models
↓
Services
↓
Persistence
```

Each layer has one responsibility.

## Routing

Routing decides where, not what. Routers should remain extremely small.

## Domain Models

Domain models represent concepts. Examples: Player, Game, Opportunity, Evidence,
League, Schedule, Snapshot.

They should contain behavior closely related to themselves. Favor immutable objects
whenever practical.

## Scoring

Scoring is the heart of Sports Today. Protect it.

Requirements: repeatable, deterministic, explainable, testable, league-independent
where practical.

## Evidence

Every recommendation should have evidence. Evidence is not presentation. Evidence is
part of the model. Every opportunity should naturally carry its explanation.

## Data Freshness

Freshness is a first-class concept. Never silently present stale information.

Every data source should communicate: fresh, cached, stale, unavailable.

The UI should communicate this honestly.

## Snapshots

Snapshots exist for debugging, history, future analysis, and regression testing. They
should contain enough information to recreate decisions.

## Caching

Caching is an optimization. Never let cache requirements shape business logic. The
application should remain correct without cache. Cache should only make it faster.

## Testing Philosophy

Test behavior. Not implementation. Prefer tests like "Future games are excluded."
instead of "Function X calls Function Y." The user experience matters more than
internal structure.

What is covered today, and how to run it, lives in **[Testing](TESTING.md)** — keep the
suite inventory there, not here.

## File Organization

Each directory should have a clear purpose. Avoid generic folders.

```
domain/       # normalized models
leagues/      # one adapter per league + registry
services/     # operations: data access, schedules, cache, snapshots, analytics
views/        # screens
components/   # reusable rendering helpers
styles/       # the single stylesheet
src/          # ingestion + scorers
scripts/      # CLI entry points
router.py
```

`src/` and `services/` are the one boundary worth stating explicitly, because both hold
non-UI logic. The split is **not** about who calls it — adapters and services call the
`src/` scorers at render time. It is a **dependency direction**:

- **`src/` is a leaf library.** External clients and pure parsing (`*_api.py`,
  `espn_*.py`), ingestion (`ingest.py`, `*_ingest.py`, `*_collector.py`), and the
  per-market **scorers** that rank a population from a dataframe (`*_opportunity.py`).
  It knows nothing about the app: no Streamlit, and it should import nothing from
  `services/`, `views/`, `components/`, `domain/`, or `leagues/`.
- **`services/` sits above it** and may freely import `src/`. Reads bounded by `as_of`,
  schedules, cache, snapshots, migrations, grading, and the per-league `*_analytics` /
  `*_game_page` builders.

So: **would this module still make sense with the app deleted?** If yes it belongs in
`src/`; if it exists to serve a screen or the daily pipeline, it belongs in `services/`.

`src/` **may** import `domain/`, which is the bottom layer: normalized models and the
market registry, depending on nothing but the standard library. That is a downward
import, not a cycle.

**This is enforced, not remembered.** `tests/test_layering.py` parses every module's
imports — including function-local ones — and fails if `src/` reaches into
`services/`, `views/`, `components/`, `leagues/`, `router`, or `app`, if `domain/`
stops being a pure leaf, or if `src/` imports Streamlit. When it fails, the fix is to
move the shared piece **down** (into `src/` or `domain/`) or move the module **up**
into `services/` — not to add an exception.

## CSS

One design system. One source of truth. Avoid page-specific styling unless absolutely
necessary.

## Naming

Names should reveal intent. Prefer `OpportunitySnapshot` over `DataRecord`. Prefer
`LeagueAdapter` over `LeagueHelper`.

If something needs a comment to explain its purpose, consider renaming it.

## Complexity Budget

Complexity is expensive. Spend it carefully. Prefer straightforward code over clever
code. Future readability is more valuable than present elegance.

## Performance

Optimize only after correctness. Readable code first. Fast code second.

## Logging

Logs should answer: What happened? Why? What data was used?

Avoid noisy logs. Avoid silent failures.

## Errors

Errors should be actionable.

Bad:

```
Failed.
```

Good:

```
Live schedule unavailable.
Using cached schedule from July 14.
Data freshness: 1 day old.
```

## Future Features

The architecture should make these additions feel natural:

- NBA
- NFL
- NHL
- MLS
- College Football
- Player profiles
- Historical comparisons
- Notifications
- Personalization
- Machine learning

If adding a new league requires editing dozens of files, the architecture should be
reconsidered.

## AI Principles

AI enhances. AI never replaces transparency. Users should always understand why a
recommendation exists. Explainability is more valuable than novelty.

## Code Review Checklist

Before merging:

- Is this easier to understand?
- Is duplication reduced?
- Does this follow the product architecture?
- Can this be tested?
- Does this introduce hidden coupling?
- Does this improve future extensibility?

If not, consider another approach.

## Definition of Success

A new engineer should be able to answer:

- Where does this feature live?
- Where is this data loaded?
- Where is this calculated?
- Where is this displayed?

without searching the entire repository.

Architecture succeeds when the correct place to add new code is obvious.

## Final Principle

The architecture should quietly disappear. Engineers should spend their time thinking
about sports, not navigating code.
