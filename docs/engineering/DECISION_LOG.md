# Decision Log

> **Purpose** — A living record of significant product and engineering decisions: what we decided, why, the tradeoffs, and what to revisit. Read this before proposing a change that reverses one of these.
> **Audience** — Engineers, product, design, and AI assistants.
> **Update when** — A significant decision is made or reversed. Append a new entry; don't rewrite history — supersede it.
> **Related** — [Architecture](ARCHITECTURE.md) · [Vision](../product/VISION.md) · [Design System](../design/DESIGN_SYSTEM.md) · [Docs index](../README.md)

Newest first. Each entry: **Decision · Reason · Tradeoffs · Future considerations.**

---

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
[MLS Provider Audit](MLS_PHASE3A_PROVIDER_AUDIT.md).

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
repository) per [MLS Phase 1 Inspection](MLS_PHASE1_INSPECTION.md) §13; then flip
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
