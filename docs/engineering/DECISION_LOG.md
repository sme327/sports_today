# Decision Log

> **Purpose** — A living record of significant product and engineering decisions: what we decided, why, the tradeoffs, and what to revisit. Read this before proposing a change that reverses one of these.
> **Audience** — Engineers, product, design, and AI assistants.
> **Update when** — A significant decision is made or reversed. Append a new entry; don't rewrite history — supersede it.
> **Related** — [Architecture](ARCHITECTURE.md) · [Vision](../product/VISION.md) · [Design System](../design/DESIGN_SYSTEM.md) · [Docs index](../README.md)

Newest first. Each entry: **Decision · Reason · Tradeoffs · Future considerations.**

---

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
