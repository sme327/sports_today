# Architecture

> **Purpose** — How the codebase is organized and the principles that keep it maintainable as leagues and features grow.
> **Audience** — Engineers and AI assistants writing code.
> **Update when** — A structural pattern, layer boundary, or naming convention changes. Log the decision in [DECISION_LOG](DECISION_LOG.md).
> **Related** — [Decision Log](DECISION_LOG.md) · [Testing](TESTING.md) · [Setup](SETUP.md) · [Vision](../product/VISION.md) · [Docs index](../README.md)

---

## Where things live (quick reference)

| To add… | Put it in… |
| --- | --- |
| a new **league** | `leagues/<name>/adapter.py` implementing `LeagueAdapter`, then `register(...)` and import it in `leagues/__init__.py` |
| a new **screen/view** | `views/<name>.py`, dispatched from `router.py` |
| a new **component** (reusable UI/HTML) | `components/<name>.py` |
| a new **service** (data, schedules, cache, snapshots, migrations) | `services/<name>.py` |
| a new **domain object** | `domain/models.py` |
| a **style/token** | `styles/app.css` (one stylesheet) |
| a **test** | `tests/test_<area>.py` (offline; no network) |

Ingestion and lower-level data collection live in `src/` (kept from the original
build). Everything else follows the layers below.

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
  context.

---

# Purpose

Architecture exists to make the product easier to evolve.

Not to impress engineers.

Not to maximize abstraction.

Not to demonstrate design patterns.

Every architectural decision should answer one question:

> **Will this make Sports Today easier to improve next year?**

---

# The Prime Directive

Every feature should be easy to understand.

If a new engineer cannot locate where a feature lives within a few minutes,

the architecture has failed.

---

# Guiding Principles

## 1. Organize around the product

Code should reflect how users think.

Not how frameworks think.

Good

```
Today

Tomorrow

Game

Player

League

Opportunity
```

Less good

```
helpers

utils

misc

common

functions

services2
```

The folder structure should mirror the product.

---

## 2. Domains own behavior

A Player should know what a Player is.

A Game should know what a Game is.

An Opportunity should know what an Opportunity is.

Avoid passing dictionaries through the application.

Favor meaningful domain models.

---

## 3. Views are dumb

Views render information.

Views do not perform business logic.

Views should answer:

"What should be displayed?"

Never:

"How should opportunities be calculated?"

---

## 4. Services do work

Services perform operations.

Examples:

schedule loading

database access

snapshot writing

caching

migrations

external APIs

Services should never contain UI.

---

## 5. Adapters isolate leagues

Every league should implement the same contract.

The rest of the application should not care whether the data comes from:

MLB

NBA

NFL

WNBA

World Cup

or something not yet imagined.

Adding a new league should require:

- one adapter
- one registry entry

Nothing else.

---

## 6. Prefer composition over inheritance

Small focused objects.

Small focused functions.

Compose behavior.

Avoid deep inheritance trees.

---

## 7. Avoid global state

Global state becomes hidden coupling.

Pass dependencies explicitly.

Cache intentionally.

Never rely on magic.

---

## 8. Explicit beats implicit

Good

```
as_of

league

game_date

mode
```

Bad

```
current

active

latest

selected
```

Variables should explain themselves.

---

## 9. Make invalid states difficult

Architecture should prevent mistakes.

Example:

A scoring engine should not be capable of accidentally loading future games.

Prevent leakage structurally.

Do not rely on discipline.

---

# Product Layers

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

---

# Routing

Routing decides

where

not

what.

Routers should remain extremely small.

---

# Domain Models

Domain models represent concepts.

Examples

Player

Game

Opportunity

Evidence

League

Schedule

Snapshot

They should contain behavior closely related to themselves.

Favor immutable objects whenever practical.

---

# Scoring

Scoring is the heart of Sports Today.

Protect it.

Requirements:

repeatable

deterministic

explainable

testable

league-independent where practical

---

# Evidence

Every recommendation should have evidence.

Evidence is not presentation.

Evidence is part of the model.

Every opportunity should naturally carry its explanation.

---

# Data Freshness

Freshness is a first-class concept.

Never silently present stale information.

Every data source should communicate:

fresh

cached

stale

unavailable

The UI should communicate this honestly.

---

# Snapshots

Snapshots exist for:

debugging

history

future analysis

regression testing

They should contain enough information to recreate decisions.

---

# Caching

Caching is an optimization.

Never let cache requirements shape business logic.

The application should remain correct without cache.

Cache should only make it faster.

---

# Testing Philosophy

Test behavior.

Not implementation.

Prefer tests like:

"Future games are excluded."

instead of

"Function X calls Function Y."

The user experience matters more than internal structure.

---

# File Organization

Each directory should have a clear purpose.

Example

```
domain/

leagues/

services/

views/

components/

styles/

router.py
```

Avoid generic folders.

---

# CSS

One design system.

One source of truth.

Avoid page-specific styling unless absolutely necessary.

---

# Naming

Names should reveal intent.

Prefer

```
OpportunitySnapshot
```

over

```
DataRecord
```

Prefer

```
LeagueAdapter
```

over

```
LeagueHelper
```

If something needs a comment to explain its purpose,

consider renaming it.

---

# Complexity Budget

Complexity is expensive.

Spend it carefully.

Prefer straightforward code over clever code.

Future readability is more valuable than present elegance.

---

# Performance

Optimize only after correctness.

Readable code first.

Fast code second.

---

# Logging

Logs should answer:

What happened?

Why?

What data was used?

Avoid noisy logs.

Avoid silent failures.

---

# Errors

Errors should be actionable.

Bad

```
Failed.
```

Good

```
Live schedule unavailable.

Using cached schedule from July 14.

Data freshness: 1 day old.
```

---

# Future Features

The architecture should make these additions feel natural:

NBA

NFL

NHL

MLS

College Football

Player profiles

Historical comparisons

Notifications

Personalization

Machine learning

If adding a new league requires editing dozens of files,

the architecture should be reconsidered.

---

# AI Principles

AI enhances.

AI never replaces transparency.

Users should always understand why a recommendation exists.

Explainability is more valuable than novelty.

---

# Code Review Checklist

Before merging:

Is this easier to understand?

Is duplication reduced?

Does this follow the product architecture?

Can this be tested?

Does this introduce hidden coupling?

Does this improve future extensibility?

If not,

consider another approach.

---

# Definition of Success

A new engineer should be able to answer:

Where does this feature live?

Where is this data loaded?

Where is this calculated?

Where is this displayed?

without searching the entire repository.

Architecture succeeds when the correct place to add new code is obvious.

---

# Final Principle

The architecture should quietly disappear.

Engineers should spend their time thinking about sports,

not navigating code.