# Product Roadmap

> **Purpose** — Where Sports Today is going, organized around the user's day rather than around technology.
> **Audience** — Product, design, engineering, and AI assistants planning what to build next.
> **Update when** — Priorities shift or a phase ships. Keep it experience-first.
> **Related** — [Vision](VISION.md) · [Experience Principles](EXPERIENCE_PRINCIPLES.md) · [Architecture](../engineering/ARCHITECTURE.md) · [Docs index](../README.md)

_Last updated: July 2026._

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
  1+ hit; WNBA points/rebounds/assists)*
- **Evidence & risk** — every opportunity shows why it stands out and what could
  go wrong. *(shipped)*
- **Game previews / deep dives** — Teams and Players tabs. *(shipped for MLB)*
- **Better inputs** — probable pitchers & handedness, confirmed lineups, expected
  plate appearances / minutes, park & weather, bullpen/rest. *(next)*
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
- **Live Refresh V2** *(follow-on)* — auto-rerun **only while at least one game is
  live**; no polling when every game is pregame or final; refresh interval TBD after
  observing source reliability (candidates: `st.fragment(run_every=…)` or
  `streamlit-autorefresh`). Until then, the 120 s cache TTL + manual refresh apply.
- **Live opportunity tracking** — is the pick on pace?
- **Win probability, momentum swings, close-game alerts.** *(future)*

### 🌙 After Games — "What just happened, and did it matter?"

- **Result tracking** — did today's opportunities hit? *(foundation shipped: daily
  snapshots capture the ranking; grading is next)*
- **Evening recap** — "What mattered tonight."
- **Signal evaluation** — which analytical signals were actually useful over time.

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
registry entry — see [Architecture](../engineering/ARCHITECTURE.md)). Planned:
NBA, NFL, NHL, MLS, College Football/Basketball, MLB postseason, and beyond.

### Intelligence & explainability

Improve recommendation quality **without** sacrificing transparency: multi-factor
scoring, trend/regression detection, injury & lineup context, rest/travel/weather,
historical matchup context, and eventually calibrated confidence. Every gain must
stay explainable — evidence is part of the model, not decoration.

### Personalization

Favorite teams / leagues / players, watchlists, and notification preferences —
always optional, always editorially driven, never intrusive.

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

- **Before Games:** better opportunity inputs (probable pitchers, lineups,
  expected volume) and cleaner game pages.
- **After Games:** grade the daily snapshots (did opportunities hit?).
- **Foundations:** NBA support; continued caching/startup improvements; continued
  design refinement.

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
