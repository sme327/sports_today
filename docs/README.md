# Sports Today — Documentation

> **Purpose** — The map of the knowledge base. Start here to find the right document.
> **Audience** — Everyone: contributors, new engineers, and AI assistants.
> **Update when** — A document is added, moved, or retired.
> **Related** — [Repo README](../README.md) · [CLAUDE.md](../CLAUDE.md)

Sports Today is a **daily sports companion, not a dashboard** — everything here
serves that idea. Documentation is grouped by concern. Every document opens with a
Purpose / Audience / Update-when / Related header so ownership is clear.

## Product — *why and what*

| Document | Read it for |
| --- | --- |
| [Vision](product/VISION.md) | Why the product exists, positioning, the decision filter. |
| [Experience Principles](product/EXPERIENCE_PRINCIPLES.md) | The UX constitution — how every screen should feel. |
| [Roadmap](product/ROADMAP.md) | Where we're going, organized around the user's day. |
| [Future Endeavors](product/FUTURE_ENDEAVORS.md) | The next major product tracks (Preview / Live / Postgame) and how they connect. |
| [WNBA Matchup Spec (v2)](WNBA_Matchup_Page_Specification_v2.md) | Source product spec for the WNBA matchup page. |
| [MLS Matchup Philosophy](MLS_MATCHUP_PHILOSOPHY.md) | Product/UX philosophy for a future MLS matchup page. |

## Design — *how it looks and feels*

| Document | Read it for |
| --- | --- |
| [Design System](design/DESIGN_SYSTEM.md) | Color, type, spacing, radius, shadow, motion, components. Mirrors `styles/app.css`. |

## Engineering — *how it's built*

| Document | Read it for |
| --- | --- |
| [Architecture](engineering/ARCHITECTURE.md) | Structure, layers, "where to add X", glossary. |
| [MLB Game Page](engineering/MLB_GAME_PAGE.md) | The MLB game preview: sections, data sources, formulas, Phase 2 hooks. |
| [WNBA Game Page](engineering/WNBA_GAME_PAGE.md) | The WNBA matchup preview: sections, basketball analytics, honest gaps. |
| [MLS Phase 1 Inspection](engineering/MLS_PHASE1_INSPECTION.md) | Read-only inspection + plan for a future MLS matchup page (reuse, data gaps, risks, sequence). |
| [Decision Log](engineering/DECISION_LOG.md) | Why things are the way they are; what not to reverse blindly. |
| [Testing](engineering/TESTING.md) | What's covered, how to run tests. |
| [Setup](engineering/SETUP.md) | One-time install and the daily data/run workflow. |

## AI

AI guidance lives in the root **[CLAUDE.md](../CLAUDE.md)** (auto-loaded by Claude
Code). It's intentionally lean and points into the docs above rather than
restating them.

## History — *point-in-time records*

Archival only; not current guidance. See
[history/](history/): the original build brief, the cleanup brief, the
architecture audit, and the migration notes.

---

### One idea to carry everywhere

> Sports Today helps users understand **what matters today**. If a document,
> feature, or screen doesn't reinforce that, question it.
