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
a sportsbook, dashboard, or fantasy platform. Supported today: MLB (1+ hit and
total bases for batters; SP strikeouts and SP hits allowed, both over/under) and
WNBA (points/rebounds/assists) opportunities, MLB/WNBA/MLS matchup pages, plus
**schedule-only** leagues (World Cup, NFL — preseason included) that appear in the
slate for awareness with no analysis. Picks are recorded and graded daily
(hit/miss/void) split across a **Daily Results** view and a **Performance**
dashboard — see [Roadmap → After Games](docs/product/ROADMAP.md) and the
[Decision Log](docs/engineering/DECISION_LOG.md).

## Read before you build

- **Product** — [Vision](docs/product/VISION.md) · [Experience Principles](docs/product/EXPERIENCE_PRINCIPLES.md) · [Roadmap](docs/product/ROADMAP.md)
- **Design** — [Design System](docs/design/DESIGN_SYSTEM.md) (mirrors `styles/app.css`)
- **Engineering** — [Architecture](docs/engineering/ARCHITECTURE.md) (structure, "where to add X", glossary) · [Decision Log](docs/engineering/DECISION_LOG.md) · [Testing](docs/engineering/TESTING.md) · [Setup](docs/engineering/SETUP.md)

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

## Known limitations

- Current season only; plate-appearance grain (no Statcast/exit velo/pitch type).
- Season-to-date feed must be replaced daily; schedules need internet.
- MLB batter scoring now uses **today's confirmed lineups** when posted (from MLB
  StatsAPI): a confirmed slot adds evidence, a scratched batter is capped, and an
  un-posted lineup is shown honestly (never guessed). Scoring still does **not**
  include opposing-starter quality, weather, park, or bullpen context. Do not
  represent scores as hit probabilities.
