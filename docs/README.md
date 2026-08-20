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
| [Sport Plans](product/SPORT_PLANS.md) | The by-sport view: each sport's status + tiered path, incl. the NFL deep-dive spec. |
| [Future Endeavors](product/FUTURE_ENDEAVORS.md) | The next major product tracks (Preview / Live / Postgame) and how they connect. |
| [Picks Shortlist](product/PICKS_SHORTLIST.md) | The approved, not-yet-built plan for selecting props into a shareable device-local shortlist. |
| [WNBA Matchup Spec (v2)](engineering/WNBA_Matchup_Page_Specification_v2.md) | Source product spec for the WNBA matchup page. |
| [MLS Matchup Philosophy](engineering/MLS_MATCHUP_PHILOSOPHY.md) | Product/UX philosophy for the MLS matchup page. |
| [MLS Matchup Blueprint (v2)](engineering/MLS_MATCHUP_PAGE_V2_BLUEPRINT.md) | The v2 section-by-section blueprint the philosophy feeds into. |

## Design — *how it looks and feels*

| Document | Read it for |
| --- | --- |
| [Design System](design/DESIGN_SYSTEM.md) | Color, type, spacing, radius, shadow, motion, components. Mirrors `styles/app.css`. |

## Engineering — *how it's built*

| Document | Read it for |
| --- | --- |
| [Architecture](engineering/ARCHITECTURE.md) | Structure, layers, "where to add X", glossary. |
| [MLB Matchup Page — Handoff](engineering/MLB_MATCHUP_PAGE_HANDOFF.md) | Pick-up-and-go briefing: what the MLB page shows, why, and where to refine/expand. Start here. |
| [MLB Game Page](engineering/MLB_GAME_PAGE.md) | The MLB game preview: sections, data sources, formulas, Phase 2 hooks (deeper reference). |
| [WNBA Game Page](engineering/WNBA_GAME_PAGE.md) | The WNBA matchup preview: sections, basketball analytics, honest gaps. |
| [MLS Game Page](engineering/MLS_GAME_PAGE.md) | The MLS matchup preview: sections, the real team-data pipeline, analytical definitions, honest gaps. |
| [NFL Game Page](engineering/NFL_GAME_PAGE.md) | The NFL matchup deep-dive: the season-feed pipeline, analytics, player spotlights, and the bridge that joins the live slate to it (and when it honestly cannot). |
| [Method](engineering/METHOD.md) | **How we decide whether a signal is real.** The tests that gate every scoring and editorial change — read before proposing one. |
| [Prediction Evaluation](engineering/PREDICTION_EVALUATION.md) | Public cohorts, grading truth, model-version discipline, and promotion guardrails. |
| [CBB](engineering/CBB.md) | College basketball: what the ingested data holds, why it stays team-level, and the phased plan. |
| [Structure Review 2026-08-17](engineering/STRUCTURE_REVIEW_2026-08-17.md) | Post-migration audit: what was removed, what is duplicated, what the docs still get wrong. |
| [UX Review 2026-08-17](design/UX_REVIEW_2026-08-17.md) | The published site as a phone reader meets it — findings and ranked fixes. |
| [Decision Log](engineering/DECISION_LOG.md) | Why things are the way they are; what not to reverse blindly. |
| [Historical Data](engineering/HISTORICAL_DATA.md) | Ingested box-score history: coverage, gaps, and which model ideas are already tested and dead. |
| [Testing](engineering/TESTING.md) | What's covered, how to run tests. |
| [Setup](engineering/SETUP.md) | One-time install and the daily data/run workflow. |
| [Deploy](engineering/DEPLOY.md) | Publish the static Django-rendered site to Cloudflare Pages from the local Mac. |
| [Django Migration](engineering/DJANGO_MIGRATION.md) | How the public site replaced Streamlit (**completed 2026-08-17**); the runbook and what the two surfaces shared. |

## AI

AI guidance lives in the root **[CLAUDE.md](../CLAUDE.md)** (auto-loaded by Claude
Code). It's intentionally lean and points into the docs above rather than
restating them.

## History — *point-in-time records*

Archival only; **not current guidance** — these describe the state of the world on the
day they were written. See [history/](history/):

| Document | Records |
| --- | --- |
| [Agent Build Brief](history/AGENT_BUILD_BRIEF.md) | The original build brief. |
| [Architecture Audit](history/ARCHITECTURE_AUDIT.md) | The pre-cleanup audit of the original structure. |
| [Architecture Cleanup Brief](history/ARCHITECTURE_CLEANUP_BRIEF.md) | The plan that produced today's layering. |
| [Migration Notes](history/MIGRATION_NOTES.md) | What moved where during that cleanup. |
| [MLS Phase 1 Inspection](history/MLS_PHASE1_INSPECTION.md) | The read-only inspection + build sequence (steps 1–6 shipped). |
| [MLS Provider Audit](history/MLS_PHASE3A_PROVIDER_AUDIT.md) | What ESPN provided for MLS at Phase 3A, and field reliability. |

---

### One idea to carry everywhere

> Sports Today helps users understand **what matters today**. If a document,
> feature, or screen doesn't reinforce that, question it.
