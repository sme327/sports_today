# MLS Matchup Page

> **Purpose** — How the MLS matchup page is built: its sections, data states, what is real today, and what is honestly deferred until a soccer-stats pipeline exists.
> **Audience** — Engineers and AI assistants extending the MLS page (and a template for a future NBA/soccer page).
> **Update when** — Sections, data states, formulas, or supported data change.
> **Related** — [Architecture](ARCHITECTURE.md) · [MLS Phase 1 Inspection](MLS_PHASE1_INSPECTION.md) · [MLS Philosophy](../MLS_MATCHUP_PHILOSOPHY.md) · [MLS Blueprint](../MLS_MATCHUP_PAGE_V2_BLUEPRINT.md) · [Decision Log](DECISION_LOG.md) · [Testing](TESTING.md)

A soccer-designed matchup preview that answers one question: **"what kind of match
am I about to watch?"** It reuses the shared architecture (router → view → cached
builder → immutable model → pure-HTML components) and the design system, and adds
soccer-specific pieces (form dots, a tactical lean bar, a formation pitch, a
"what to watch" timeline).

This is the **reference implementation for future soccer coverage**. Its defining
idea is **progressive intelligence over a fixed layout**: the page shell and every
component ship now; sections that need data we do not yet collect render in an
honest **data state** and fill in later without a redesign.

## Flow

```
router → views/game.py (dispatch: league == "MLS")
       → views/mls_game.py (renders sections in blueprint order)
       → services/app_cache.cached_mls_game_page  (cache: game_id | as_of | engine version)
       → services/mls_game_page.build_mls_game_page  (deterministic builder)
       → domain/mls_game_page.MLSGamePage  (immutable model; per-section DataState)
       → components/mls_game.py  (pure HTML; shared section shell + soccer pieces)
```

Schedule comes from `src/espn_soccer.py` (a neutral, competition-parameterized
ESPN soccer client; MLS = `usa.1`) via `leagues/mls/adapter.py`. Cached on
`game_id | as_of | mls-game-page-v1`.

## Data states (the honesty model)

Every section carries a `DataState`, rendered as a badge. The layout is identical
across states; only the intelligence and the badge change.

| State | Badge | Meaning |
|---|---|---|
| `AVAILABLE` | Live | Real, trustworthy data (or clearly-labeled generic guidance). |
| `PARTIAL` | Partial | Some rows real, others awaiting collection. |
| `PROJECTED` | Projected | A best-effort estimate, clearly labeled (e.g. an unconfirmed lineup). |
| `UNAVAILABLE` | Coming soon | The supporting pipeline is not built yet; shown honestly, never faked. |

**Non-negotiable:** `UNAVAILABLE`/`PROJECTED` sections render their real component
shell with an honest explanation — **never fabricated numbers or team-specific
tactical claims.** This is the product's "be honest about data" rule made structural.

## Sections (blueprint order)

1. **Hero** — teams, club logos, W-D-L records, points, recent form (W/D/L dots),
   competition, kickoff, venue, broadcast, and live/final score. **All real.**
2. **Matchup Snapshot** — `PARTIAL`. Record, points, and last-5 form are real;
   goals, possession, shots, and passing are `UNAVAILABLE` placeholder rows.
3. **Tactical Matchup** ⭐ — the signature framework: nine style dimensions
   (possession, pressing, defensive line, width, transition speed, set-piece
   danger, crossing, directness, game control), each a home/even/away lean bar
   with a one-line reason. `UNAVAILABLE` in V1 (no team style data yet); the
   framework renders so the read is stable when data arrives.
4. **Key Storylines** — `AVAILABLE` when triggered. A small deterministic engine
   over the **real** record + form: a record-contrast storyline (season-long,
   Moderate confidence) and per-team "in form"/"searching for form" storylines
   (last-5, Low confidence). W/D/L counts are **order-independent**, so no claim
   depends on the feed's (unreliable) result ordering.
5. **Projected Lineups** — `UNAVAILABLE`. A CSS/SVG formation pitch renders a
   neutral 4-3-3 of empty slots per team, labeled "layout shown for reference, not
   a projection." Degrades gracefully (stacks) rather than disappearing.
6. **Players to Watch** — `UNAVAILABLE`. Five role archetypes (Finisher, Creator,
   Ball progressor, Defensive anchor, Goalkeeper) shown as awaiting squad data.
7. **Attacking Profile** — `UNAVAILABLE`. Six style dimensions (build-up,
   transitions, crossing, through balls, set pieces, long-range) as awaiting rows.
8. **Discipline** — `UNAVAILABLE`. Cards / fouls / suspensions as awaiting rows.
9. **What to Watch Timeline** ⭐ — `AVAILABLE`. Six phases (Pregame → Opening →
   Midfield → Tactical shift → Late match → Substitutions) with **generic,
   clearly-labeled** match-watching guidance (education, not a team-specific
   prediction). Team-specific cues arrive with the tactical model.
10. **Honest Gaps** — the real list of what we do not know yet and why.
11. **Data Context** — provenance line (source, as_of, what is live).

## Data & engine

- **Source:** `src/espn_soccer.py` → ESPN `usa.1` scoreboard. Real per-game:
  teams, club logos, brand colors, W-D-L records, recent form, venue, kickoff,
  broadcast, and Final-score V1 fields. The adapter stashes the soccer-specific
  extras (records, form, colors, competition) in `SlateGame.meta`.
- **Builder** (`services/mls_game_page.py`, `ENGINE_VERSION = "mls-game-page-v1"`):
  deterministic, no generative text. The only V1 "intelligence" is the storyline
  engine over real record + form. Everything else composes honest states.
- **Team color safety:** brand colors from ESPN are contrast-guarded at render
  time (`components/mls_game._safe_accent`) so a dark primary (e.g. a black) never
  disappears on the charcoal canvas; missing colors fall back to the brand orange.

## Not shown in this version (honest gaps)

Confirmed/projected lineups, season match stats (goals/shots/possession/passing),
team tactical style, player match stats and availability, discipline records, and
advanced tracking (xG, pressing intensity, heat maps). None are collected or
claimed — each renders as an honest state, not a guess.

## Progressive intelligence (how it grows without a redesign)

| Version | What changes | Layout |
|---|---|---|
| **V1 (this)** | Rule-based; real hero + snapshot + storylines; the rest honest states. | fixed |
| **V1.5** | Match-stats collection → snapshot/attacking/discipline become real; tactical leans resolve. | fixed |
| **V2** | Formation-aware; projected then confirmed lineups populate the pitch. | fixed |
| **V3** | Advanced tracking (xG, pressing) and live tactical cues. | fixed |

The next build step is the **soccer data pipeline** (collector + additive tables +
repository), following the sequence in [MLS Phase 1 Inspection](MLS_PHASE1_INSPECTION.md)
§13. Until it exists, no section fabricates data.

## Extension points

- `src/espn_soccer.py` is competition-agnostic — other soccer competitions (and,
  eventually, a migration of World Cup) can reuse it by slug.
- Each section is an independent `DataState` swap: wiring real data means changing
  a builder function and a state, not the view or the CSS.
