# MLS Matchup Page

> **Purpose** — How the MLS matchup page is built: its sections, the real team-data pipeline behind them, the exact analytical definitions, and what is honestly deferred.
> **Audience** — Engineers and AI assistants extending the MLS page (and a template for a future NBA/soccer page).
> **Update when** — Sections, data states, formulas, thresholds, collected data, or the pipeline change.
> **Related** — [Architecture](ARCHITECTURE.md) · [MLS Provider Audit](MLS_PHASE3A_PROVIDER_AUDIT.md) · [MLS Phase 1 Inspection](MLS_PHASE1_INSPECTION.md) · [Philosophy](../MLS_MATCHUP_PHILOSOPHY.md) · [Blueprint](../MLS_MATCHUP_PAGE_V2_BLUEPRINT.md) · [Decision Log](DECISION_LOG.md) · [Testing](TESTING.md)

A soccer-designed matchup preview that answers **"what kind of match am I about to
watch?"** It reuses the shared architecture (router → view → cached builder →
immutable model → pure-HTML components) and adds soccer-specific pieces (W/D/L form
dots, a tactical lean bar, a CSS/SVG formation pitch, a "what to watch" timeline).

Its defining idea is **progressive intelligence over a fixed layout**: the shell and
every component ship once; each section carries a `DataState`, and real data drops in
by flipping a state — never by a redesign. **As of the team-data integration, the
team-level analysis is real** (collected ESPN box scores); player- and event-level
sections remain honestly unavailable.

## Flow

```
router → views/game.py (dispatch: league == "MLS")
       → views/mls_game.py (renders sections in blueprint order)
       → services/app_cache.cached_mls_game_page  (cache: game_id | as_of | engine version)
       → services/mls_game_page.build_mls_game_page  (deterministic builder)
             ├── services/mls_repository   (leakage-safe reads of collected team data)
             └── services/mls_analytics     (tactical proxies + storyline rules)
       → domain/mls_game_page.MLSGamePage  (immutable model; per-section DataState)
       → components/mls_game.py  (pure HTML; shared section shell + soccer pieces)

collection (offline, separate from the app):
  src/mls_collector.py → src/espn_soccer.py (summary/standings parsers)
                       → services/mls_store.py (additive SQLite tables + upserts)
```

The schedule (and hero) come from `src/espn_soccer.py` (a neutral,
competition-parameterized ESPN client; MLS = `usa.1`) via `leagues/mls/adapter.py`,
which also carries the stable `team_id`s. Builder cached on
`game_id | as_of | mls-game-page-v2`.

## Data states (the honesty model)

Every section carries a `DataState`, rendered as a badge. Layout is identical across
states; only the intelligence and the badge change.

| State | Badge | Meaning |
|---|---|---|
| `AVAILABLE` | Live | Real, trustworthy data (or clearly-labeled generic guidance). |
| `PARTIAL` | Partial | Some rows real, others awaiting collection. |
| `PROJECTED` | Projected | A best-effort estimate, clearly labeled (e.g. an unconfirmed lineup). |
| `UNAVAILABLE` | Coming soon | The supporting pipeline is not built yet; shown honestly, never faked. |

**Non-negotiable:** `UNAVAILABLE`/`PROJECTED` sections render their real component
shell with an honest explanation — **never fabricated numbers or team-specific
tactical claims.**

## Sections (current states)

When collected team data exists strictly before the match date for **both** clubs
(≥ 4 matches each), the analytical sections build from real aggregates; otherwise they
fall back to the honest awaiting-data states.

1. **Hero** — `AVAILABLE`. Teams, logos, W-D-L records, points, recent form dots,
   competition, kickoff, venue, broadcast, live/final score, **plus real conference
   standing** (e.g. "6th in West · 24 pts").
2. **Matchup Snapshot** — `AVAILABLE` (**outcomes**): goals/match, goals allowed/match,
   goal difference/match, shots/match, shots on target/match, Ball Share, and
   Points/match (venue) — the home club's home form vs the away club's away form.
3. **Tactical Matchup** ⭐ — `AVAILABLE` (**measured style contrasts**): Passing
   Completion, Defensive Shot Pressure, Corner Pressure. Only dimensions with a real
   edge are shown; fewer than two → a compact *similar-profile* line scoped to style
   (never contradicting a lopsided Snapshot). **No claims** about pressing, low blocks,
   transitions, width, directness, or line height.
4. **Key Storylines** — deterministic rules over real aggregates, recent results, and
   the table; the strongest 3–5, deduped by theme. Three honest empty states:
   real-but-no-trigger (`AVAILABLE`, "No standout storylines"), `PARTIAL` (thin sample),
   `UNAVAILABLE` (no collected data → record/form fallback).
5. **Projected Lineups** — `UNAVAILABLE`. A CSS/SVG reference pitch (empty 4-3-3 slots),
   clearly "layout shown for reference, not a projection." Degrades gracefully.
6. **Players to Watch** — `UNAVAILABLE`. Five role archetypes; the feed lacks per-player
   minutes/passing/defensive actions, so it stays honest rather than guessing.
7. **Attacking Profile** — `AVAILABLE` (**volume/finishing**): shot accuracy, crossing
   volume, cross accuracy, penalty attempts/match. Near-identical rows are suppressed;
   all suppressed → a compact summary.
8. **Discipline** — `AVAILABLE`. Fouls/match, yellow cards/match, red cards (season
   count, with sample size). Compact; if both clubs are unremarkable → a summary line.
9. **What to Watch Timeline** ⭐ — `AVAILABLE`. Six phases of **generic, clearly-labeled**
   match-watching guidance (education, not a team-specific prediction).
10. **Honest Gaps** — a dynamic list of what we don't know yet and why (updates once
    team data is present).
11. **Data Context** — provenance line (source, as_of, sample sizes).

## Data & engine

### Collection (offline)
- **`src/espn_soccer.py`** — neutral ESPN soccer client. Beyond the scoreboard it adds
  `fetch_summary` / `fetch_standings` and **pure parsers** (`parse_team_stats`,
  `parse_match_meta`, `parse_standings`). No orchestration/SQLite/retries live here.
- **`src/mls_collector.py`** — regular-season, completed-only collector (WNBA-collector
  pattern): scoreboard discovery, incremental skip, retries/backoff, explicit validation
  (2 competitors, IDs reconcile, 2 team-stat blocks), idempotent upserts, standings
  refresh, audit run, CSV mirror. **Never writes partial/fabricated rows.**
- **`services/mls_store.py`** — additive tables + upserts: `mls_matches`,
  `mls_team_match_stats` (PK `event_id,team_id`), `mls_standings` (snapshot history),
  `mls_collection_runs`. Created via `services/migrations.ensure_schema`. **Missing
  provider fields stay NULL — never converted to zero.**

### Reads & analysis (in-app)
- **`services/mls_repository.py`** — leakage-safe reads. Every query includes only
  completed matches **strictly before** the match date `D`, excludes the selected match,
  and never sees a match on/after `D`. Provides season aggregates, home/away splits,
  last-5 results, league averages, standings lookup, and **sample sizes**.
- **`services/mls_analytics.py`** — deterministic engines: `proxy_dimensions` (tactical
  proxies + significance filtering) and `storylines` (rule-based, deduped).
- **`services/mls_game_page.py`** (`ENGINE_VERSION = "mls-game-page-v2"`) — assembles the
  immutable page; real-data path when both clubs have ≥ 4 prior matches, else the honest
  fallback.

### Exact analytical definitions
- **Window:** completed regular-season matches with `match_date < D`, minus the selected
  event. Home split = `is_home = 1`; away split = `is_home = 0`.
- **Aggregation:** counts & possession use **per-match means**; accuracy rates
  (shot/pass/cross) use **pooled ratios** `100·Σnumerator/Σdenominator` (NULL if the
  denominator is 0). Stored `shot_pct/pass_pct/cross_pct` are **derived from raw counts**
  (the provider's `*Pct` are lossily rounded); `possession_pct` is provider-reported
  (0–100). Points/match = `(3W + D)/n` on the relevant venue split.
- **Section ownership (no metric appears twice):** Snapshot = outcomes · Tactical = style
  proxies (passing, defensive shot pressure, corners) · Attacking = finishing/crossing ·
  Discipline = fouls/cards.
- **Tactical edge:** magnitude `= |home − away| / scale`; `< 0.35 → suppressed/Even`; else
  the better side (lower-is-better for Defensive Shot Pressure). Scales: Passing
  Completion 6.0, Defensive Shot Pressure 4.0, Corner Pressure 2.5.
- **Significance suppression:** Attacking — shot accuracy ≥ 3.0 pts, crossing volume ≥
  2.5/match, cross accuracy ≥ 4.0 pts, penalty attempts ≥ 0.15/match. Discipline —
  fouls ≥ 1.0/match, yellows ≥ 0.4/match, reds shown if `max ≥ 3 or |diff| ≥ 2`.
- **Confidence:** `min(matches) ≥ 8 → Moderate`, `≥ 4 → Low`, else the dimension/section
  is omitted. No "High" (a dozen unadjusted matches is not high confidence).
- **Storyline rules** (each carries inputs, threshold, sample, confidence): strong-home
  (home PPM ≥ 2.0), weak-away (away PPM ≤ 0.9), unbeaten/losing run (last 5), scoring
  surge / defensive decline (last-5 vs season Δ ≥ 0.7), high/low shot volume (±3 vs
  league), defensive-shot-pressure concern (+3), ball-share contrast (≥ 10 pts),
  high-card matchup (≥ 4.5 combined), table gap (≥ 6 places).
- **Team color safety:** ESPN brand colors are contrast-guarded at render
  (`components/mls_game._safe_accent`) so a dark primary never disappears on the charcoal
  canvas; missing colors fall back to brand orange.

## Not shown yet (honest gaps)

Confirmed/projected lineups & formations, per-player stats (the feed lacks minutes,
passing, and defensive actions), match-event timing (goal/card/sub minutes, scorers —
collected by the provider but not yet stored), and advanced tracking (xG, pressing, heat
maps). None are claimed — each renders as an honest state. See the
[Provider Audit](MLS_PHASE3A_PROVIDER_AUDIT.md) for exact field reliability.

## Progressive intelligence & next steps

| Stage | State | What it adds | Layout |
|---|---|---|---|
| **Foundation** | ✅ shipped | Real hero + records/form + honest shells | fixed |
| **Team data (Option A)** | ✅ shipped | Real Snapshot, Tactical proxies, Attacking, Discipline, Storylines, standings | fixed |
| **Match events (Option C)** | next | Goal/card/sub timing + scorers → real timeline cues + richer storylines | fixed |
| **Confirmed lineups** | later | Projected → confirmed XI populates the pitch; formation-aware | fixed |
| **Player data (Option B)** | deferred | Position-aware Players to Watch — **blocked** until a richer player source exists | fixed |
| **Advanced / live** | future | xG, pressing, live tactical cues | fixed |

The recommended next increment is **Option C (match events)** — cheap (same summary
payload), high narrative value, no player-data dependency. Player data (Option B) is
deferred because the ESPN feed's player totals are too thin for an honest,
differentiated section.

## Extension points

- `src/espn_soccer.py` is competition-agnostic — other soccer competitions (and,
  eventually, a migration of World Cup) reuse it by slug.
- `services/mls_analytics.py` is soccer-generic and reusable for a future league page.
- Each section is an independent `DataState` swap: wiring new data means changing a
  builder function and a state, not the view or the CSS.
