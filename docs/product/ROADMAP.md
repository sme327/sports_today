# Product Roadmap

> **Purpose** — Where Sports Today is going, organized around the user's day rather than around technology.
> **Audience** — Product, design, engineering, and AI assistants planning what to build next.
> **Update when** — Priorities shift or a phase ships. Keep it experience-first.
> **Related** — [Vision](VISION.md) · [Experience Principles](EXPERIENCE_PRINCIPLES.md) · [Architecture](../engineering/ARCHITECTURE.md) · [Docs index](../README.md)

_Last updated: August 2026 (after prop grading + Results, SP pitcher props, MLB
trend spotlights, and confirmed-lineup awareness)._

---

## How to read this roadmap

Sports Today is a **daily sports companion**. So the roadmap is organized around
the **user's sports journey through a day and a season** — not around leagues,
models, or platforms. Technology exists to serve these moments.

> **Experiences drive technology. Technology supports experiences.**

Each phase below answers a question the user is actually asking at that moment.
Cross-cutting **Foundations** (leagues, platform, design) support every phase and
are listed last.

Every candidate feature is filtered by four questions (see
[Prioritization](#prioritization)). If it doesn't clearly help the moment it
belongs to, it waits — or it doesn't get built.

---

## The journey

### ☀️ Morning — "What should I pay attention to today?"

Before the user has looked at anything. The most important moment we serve.

- **Daily Briefing** — "Here's what changed overnight." *(shipped foundation: the
  Today slate; briefing narration is next)*
- **Today's storyline** — the one thing that makes today interesting.
- **Biggest opportunity** — the single strongest pick, surfaced first.
- **Watchability ranking** — "If you watch only one game…"
- **Quick recap of yesterday** — a one-line bridge from the day before.

### 🕐 Before Games — "What's worth watching, and why?"

The user is planning their day. This is where the opportunity engine lives.

- **Today's slate** — clickable game cards. *(shipped)*
- **Top Opportunities** — ranked, explainable player opportunities. *(shipped: MLB
  batter 1+ hit; MLB SP strikeouts and SP hits allowed, both over/under; WNBA
  points/rebounds/assists — all filterable by prop-type pills)*
- **Evidence & risk** — every opportunity shows why it stands out and what could
  go wrong. *(shipped; a two-up card grid keeps both blocks visible while doubling
  density)*
- **Picks shortlist** — select the props you like into a device-local, shareable
  list; the next day, Results shows your own record. *(approved 2026-08-20, next
  up — plan: [Picks Shortlist](PICKS_SHORTLIST.md))*
- **Game previews / deep dives** — editorial matchup pages. *(shipped: MLB, WNBA, and
  MLS — the latter with real collected team-stat analysis; see
  [MLS Game Page](../engineering/MLS_GAME_PAGE.md)). The MLB page also carries
  pitcher/player **trend spotlights** (per-start & per-game sparklines, windows,
  streaks).*
- **Better inputs** — *(shipped: confirmed lineups for MLB batter scoring — slot
  evidence, bench-cap, honest not-posted state; probable pitchers & handedness).*
  Still ahead: expected plate appearances / minutes, park & weather, bullpen/rest,
  matched-starter season lines; for MLS, match-event timing then confirmed lineups.
- **Watchability score, best matchup, closest games.**

### 🏟️ During Games — "What's happening right now that matters?"

Today the app is schedule-aware with **final and basic live scores** on the game
cards (Final-score V1). This phase grows carefully.

- **Live status honesty** — clear data-freshness signals. *(shipped: degraded mode)*
- **Scores on cards** — final score + winner; live score + a compact status badge.
  *(shipped: Final-score V1; parsers extract score/state/winner/status_detail, no
  endpoint or hydrate change)*
- **Live State V2** *(follow-on)* — richer in-game detail from fields the sources
  already expose: MLB inning/state/outs via a `hydrate=linescore` add; WNBA quarter
  + clock (`status.period` / `status.displayClock`); soccer match minute + status
  detail. Presentation grows to show period/clock.
- **Live Refresh V2** *(follow-on)* — refresh **only while at least one game is live**;
  no polling when every game is pregame or final. Partly shipped: the static site polls
  ESPN from the reader's browser every 60 s (`web/static/static-site.js`) and updates
  cards in place. Still open: stopping the poll once every game is final, and choosing an
  interval from observed source reliability rather than a round number.
- **Live opportunity tracking** — is the pick on pace?
- **Win probability, momentum swings, close-game alerts.** *(future)*

### 🌙 After Games — "What just happened, and did it matter?"

- **Result tracking** — did today's opportunities hit? *(shipped: the full scored
  population is recorded and graded hit/miss/void — DNP = void — split into two
  views: **Daily Results** (one slate, shared filter bar, per-market hit rates) and
  a **Performance** dashboard (calibration by score band, over-time trend, over-vs-
  under, edge finder by segment, consistency windows, by-month, model-version
  comparison). See the [Decision Log](../engineering/DECISION_LOG.md).)*
- **Evening recap** — "What mattered tonight."
- **Signal evaluation** — which analytical signals were actually useful over time.
  *(shipped as the Performance dashboard; used to drive Scoring v2 — see below.)*

### 📅 Season — "How is the bigger picture developing?"

- **Momentum** — teams quietly rising or collapsing.
- **Standings & playoff context, record watch, streaks.**
- **Season trends & pace**, historical context ("what makes tonight unusual").
- **Player & team profiles** as living, season-long destinations.

### ❄️ Offseason — "Keep me connected between games."

- **Today in history, franchise milestones, anniversaries.**
- **Historical comparisons, season memories, career pace.**
- Lighter cadence — the companion stays warm without daily games.

---

## Foundations (cross-cutting)

These support every phase of the journey.

### Leagues & coverage

Adding a league should feel routine, not like a project (one adapter + one
registry entry — see [Architecture](../engineering/ARCHITECTURE.md)). Shipped: MLB,
WNBA, World Cup (schedule), **NFL** (schedule), and **MLS** (first soccer league with a
full matchup page and collected team-stat analysis).

Expansion is **tiered** (each tier is an independent chip-away unit) and organized by
**sport family** so a foundation is built once and reused: **schedule-only** (an ESPN
adapter, ~hours) → **player props** (a game-log collector + a reachable-bar scorer) →
**matchup deep-dive**. Families: football (NFL → NCAA FB → UFL/spring), basketball
(WNBA → NBA → NCAA → March Madness), hockey (NHL — counting-stat props reuse the
reachable-bar model directly), soccer (MLS/World Cup → more leagues schedule-only,
props deferred). Postseasons/tournaments get a **Top Today** spotlight. Deliberately
out of the model: individual/event sports (golf, tennis, motorsport, combat) and
fantasy/bracket-pool management. Full sequenced plan + capability matrix live in the
project tracker.

### Intelligence & explainability

Improve recommendation quality **without** sacrificing transparency: multi-factor
scoring, trend/regression detection, injury & lineup context, rest/travel/weather,
historical matchup context, and eventually calibrated confidence. Every gain must
stay explainable — evidence is part of the model, not decoration.

### Personalization

Favorite teams / leagues / players, watchlists, and notification preferences —
always optional, always editorially driven, never intrusive. Shipped: the
**picks shortlist** (2026-08-20) — device-local prop selection with a share-as-text
tray and a next-day "Your picks: N/M" line on Results; no accounts, no odds, no
backend (see [Picks Shortlist](PICKS_SHORTLIST.md)).

### Platform & premium experience

Faster startup, better caching, offline resilience, keyboard/command navigation,
and — someday — native macOS/iOS/iPadOS apps, widgets, and Live Activities. The
app should feel exceptional on every surface.

### Craft

Continue **refining** the design system (typography, spacing, hierarchy, motion)
rather than redesigning it. See [Design System](../design/DESIGN_SYSTEM.md).

---

## Prioritization

Every candidate feature is scored on four questions:

1. Does this improve **today's** experience?
2. Does this **reduce cognitive load**?
3. Does this **improve trust**?
4. Does this **increase delight**?

If it scores poorly, it belongs later — or not at all.

---

## Current priorities (next major version)

- **Operate & accumulate:** run the daily update so the graded ledger builds up —
  the learning loop (record → grade → read by band/market) is shipped but only
  becomes informative with weeks of graded slates. This is the current bottleneck,
  not more features.
- **After Games:** the Performance dashboard (calibration by band, edge finder,
  version comparison) is shipped; it now needs **ledger depth** to sharpen — most
  segment bands are still small-sample. Next: segment-edge annotations on today's
  picks and a proven-edge confidence tier (Scoring v2 follow-ups).
- **Before Games:** further inputs beyond confirmed lineups (expected plate
  appearances/minutes, matched-starter lines, park/weather/bullpen). MLB batter
  markets (strikeouts, walks) are shipped; total bases was retired and home runs are out of scope
  (a "1+ HR" pick is only ever a ~25% longshot — poor fit for the reliability bar).
  For **MLS**, projected/confirmed lineups next; **MLS player data is deferred**
  until a richer source exists.
- **Foundations:** NBA support; WNBA player-trend parity; continued caching/startup
  and design refinement.

---

## What we will never become

A sportsbook · a fantasy platform · a statistics encyclopedia · a social network ·
a news aggregator · an advertising platform · **a dashboard filled with widgets.**

Our value comes from thoughtful curation.

---

## Someday / dream features

Intentionally ambitious, not commitments: natural-language search ("what should I
watch tonight?"), AI-generated daily briefing, Live Activities, Apple Calendar
integration, shared family dashboard, stadium explorer, personal sports journal,
season memories.

---

## Definition of success

Opening Sports Today should feel like opening a beautifully written morning
briefing — not because it contains everything, but because it contains exactly
what matters. If the product consistently answers **"What should I pay attention
to today?"**, it is succeeding.
