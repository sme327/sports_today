> 🗄️ **Historical record (2026-07-15).** Point-in-time audit that guided the
> architecture refactor. Kept for provenance; for current guidance see
> [Architecture](../engineering/ARCHITECTURE.md) and the [Decision Log](../engineering/DECISION_LOG.md).

# Sports Hub — Architecture Audit & Cleanup Plan

Status: **approved, in progress** on branch `refactor/architecture-cleanup`.
Author: Claude (Opus 4.8). Date: 2026-07-15.

This document is the deliverable requested by `CLAUDE_ARCHITECTURE_CLEANUP_BRIEF.md`.
It contains: the pre-refactor review, the owner's decisions, the implementation
plan and commit sequence, and the guarantees around persistent data and daily
workflows.

---

## Part 1 — Verification performed before any change

- App boots headless with HTTP 200 and no tracebacks.
- Data is real and healthy: **113,056** MLB plate appearances across **30** teams
  (`2026-03-25 → 2026-07-12`); **4,532** WNBA player-game rows across **188** games.
- MLB and WNBA opportunity scorers both return rows in isolation.
- Live schedule probe for 2026-07-15: **MLB 0 games**, WNBA 3, World Cup 1
  (World Cup came from live ESPN, not the hardcoded fallback). The empty MLB
  result is meaningful — see Risk R1.

---

## Part 2 — Review

### 2.1 What is working well

- **The data/ingestion layer is the strongest part of the codebase.**
  `src/ingest.py` handles the two-row vendor header, derives transparent boolean
  fields, preserves MLB IDs, and builds sensible indexes. `src/wnba_collector.py`
  has retry/backoff, upsert-by-conflict, incremental skip, a `wnba_collection_runs`
  audit table, and CSV mirrors. Minimal change is warranted here.
- **The daily download pipeline is robust and idiomatic.** `sync_mlb_download.py`
  does SHA-256 dedup, atomic temp-file replace, year-partitioned archive, collision
  handling, and a CSV history log — exactly right for an unattended double-click flow.
- **Scoring is transparent and inspectable**; both engines expose every component and
  emit human-readable support/risk strings rather than an opaque number.
- **HTML escaping is correct** everywhere values are interpolated into markup,
  including remote image URLs. No injection surface despite heavy `unsafe_allow_html`.
- **Honest empty states exist in most paths.**

### 2.2 Weaknesses

- **`app.py` is a ~1,300-line linear script** doing config, CSS, navigation, data
  loading, team normalization, two scoring integrations, and all HTML generation.
- **~370 of ~745 CSS lines are dead** — the entire `stSegmentedControl` block styles
  a widget the app no longer renders (the date switch is now custom `<a>` tags).
  `.status-chip` is defined three times; league-button styling is overridden in four
  places. Clear fingerprint of patch-on-patch growth.
- **Two contradictory navigation paradigms coexist**: query-param links (date switch,
  game selection) vs `session_state` + `st.rerun()` (league filters).
  `st.session_state.selected_day` is initialized and never read.
- **Team-identity matching is reinvented per league** with no shared contract:
  `MLB_TEAM_ALIASES` in `app.py` vs token-normalization in `wnba_opportunity.py`.
  The MLB path round-trips schedule → canonical abbr → raw PBP strings.
- **Two loaders for the same WNBA table**; `WNBA_DB_PATH` duplicates `config.DB_PATH`.
- **The `games` table is derived-but-unused and semantically fragile**
  (`road_team = first batting_team`); the app reads `plate_appearances` directly.
- **Divergent opportunity shapes** between MLB and WNBA, hand-mapped on the homepage.

### 2.3 Risks

- **R1 — The headline feature vanishes on a schedule hiccup.** Opportunities are
  computed only for teams in the live schedule. With MLB returning 0 games today,
  the entire MLB opportunity feed is empty despite 113k PAs on disk, with no
  degraded fallback.
- **R2 — No caching on schedule calls.** All three schedule endpoints are re-fetched
  on every rerun (every toggle click), each with 15–20s timeouts.
- **R3 — Unofficial, unversioned upstreams with no drift detection.** A field rename
  yields empty lists, not errors.
- **R4 — Data-leakage seam is open.** Scorers use `.tail(N)` of all PAs regardless of
  viewed date; no `as_of` parameter exists.
- **R5 — Snapshots (a stated core principle) do not exist.** Every day that passes is
  unrecoverable evaluation data.
- **R6 — No tests at all.**
- **R7 — Timezone/day-boundary mismatch** (`date.today()` local vs hardcoded Pacific
  display).
- **R8 — Unpinned dependencies, no lockfile; `plotly` required but unused.** Streamlit
  API churn is already visible.

### 2.4 Things the brief under-weighted

- Offline/degraded mode as a first-class state (not just try/except → empty).
- Schedule caching + recorded-payload parser tests (the failure that actually happens
  is JSON parsing, not team-matching logic).
- Observability (everything is `print()`).
- Provenance/freshness surfaced in the UI.
- Per-league image provenance (MLB team logo vs WNBA headshot) behind one `image_url`.
- Concurrent SQLite access (collector writes while app reads; not in WAL mode).

### 2.5 Disagreements with the brief

- **Do not use a `pages/` directory.** Streamlit auto-generates multipage nav from
  `pages/*.py`, which fights the manual same-tab query-param router. Use `views/`.
  **[Owner approved.]**
- **Validation is a CLI/diagnostic command, not a startup step** (avoids latency and
  keeps failures out of the render loop).
- **Snapshots are technically a new feature**; reconciled below by building the seam
  and writing snapshots but shipping no snapshot-review UI.
- **Pixel-exact reproduction of the dead segmented-control hacks is not a goal**; the
  live `.date-toggle` look is preserved from a clean stylesheet.
- **Highest-value tests are recorded-JSON parser tests**, weighted above team-matching.

---

## Part 3 — Owner decisions (authoritative)

1. **Snapshots** — build the storage seam **and** write daily snapshots this pass; no
   review UI yet. Records must capture enough context to interpret the ranking later.
2. **`as_of`** — wire an explicit `as_of` slate date through scoring and data access
   now. All historical windows must be computed using **only information available
   before the slate date**, preventing future-data leakage by construction.
3. **Degraded mode** — ordered fallback, with clear separation from slate analysis:
   1. Live schedule.
   2. Most recent **valid cached** schedule for that date.
   3. Explicit, **labeled** league-wide fallback ("League-wide profiles — live slate
      unavailable"). Never presented as today-specific.
   - If the schedule legitimately contains **no games**, do **not** show league-wide
     fallback.
4. **Commits** — branch `refactor/architecture-cleanup`, small reviewable commits,
   app runnable between commits.

### 3.1 Schedule cache record (owner-specified fields)

`league, slate_date, fetched_at, source, status (success/failure), payload`
(normalized games stored; raw retained where cheap). The cache is consulted **before**
any league-wide fallback so a brief API hiccup never changes the meaning of the page.

### 3.2 Snapshot record (owner-specified context)

Each snapshotted opportunity stores enough to reproduce/interpret the ranking:

`snapshot_date (slate date), calculated_at, league, game_id, player_id, team_id,
market, threshold, opportunity_score, stability_score, component_values (JSON),
support_evidence (JSON), risk_evidence (JSON), schedule_source_status,
historical_data_cutoff (as_of), lineups_available, matchup_context_available,
injury_context_available, scoring_engine_version`.

Rationale: a month later we must know **why** the score was what it was, not merely
that it was 88.

### 3.3 Adapter interface (owner-specified, explicit modes)

League-wide fallback is an **explicit mode**, never an accidental consequence of a
missing schedule:

```python
adapter.opportunities(as_of=slate_date, scheduled_team_ids=team_ids, mode="slate")
adapter.opportunities(as_of=slate_date, mode="league_wide")
```

---

## Part 4 — Target architecture

`pages/` is intentionally avoided (see 2.5).

```
app.py                 # config, CSS load, router dispatch, top-level error boundary
router.py              # query-param <-> nav state; Today vs Game dispatch; same-tab
domain/
  models.py            # SlateGame, Opportunity, Evidence, DataStatus (+ enums)
leagues/
  base.py              # LeagueAdapter Protocol + registry + OpportunityMode
  mlb/adapter.py       # schedule, team matching, opportunities(mode=...), deep dive
  mlb/teams.py         # MLB_TEAM_ALIASES + canonicalization (moved out of app.py)
  wnba/adapter.py
  world_cup/adapter.py
services/
  data_access.py       # load PA / WNBA logs with as_of filtering + freshness
  schedules.py         # cached schedule fetch: live -> cache -> failure DataStatus
  schedule_cache.py    # SQLite-backed cache (owner fields)
  snapshots.py         # write daily opportunity snapshots (owner fields)
  freshness.py         # data-through dates, collection recency
views/
  today.py             # slate + storylines + opportunity feed (degraded aware)
  game.py              # deep dive (MLB Teams/Players; WNBA/WC schedule-only)
components/
  date_switch.py  league_filters.py  game_cards.py
  opportunity_feed.py  status_chip.py  empty_states.py
styles/app.css         # single stylesheet (dead CSS removed)
diagnostics.py         # CLI validation (replaces validate_*.py), not startup
.streamlit/config.toml # theme + server settings
src/                   # ingest.py, wnba_collector.py, sync (the good parts, kept)
tests/                 # parser fixtures, team matching, empty states, routing, as_of
```

Adapters are **plain modules implementing a `Protocol`, registered in a dict** —
no class hierarchy. Adding NBA later is one module + one registry line.

---

## Part 5 — Implementation plan & commit sequence

Each step leaves the app runnable. New structure is built alongside the old; `app.py`
is switched to it near the end, so early commits cannot break the running app.

1. `chore`: init project-scoped git repo + baseline. **(done)**
2. `docs`: this `ARCHITECTURE_AUDIT.md`.
3. `refactor(domain)`: add `domain/models.py` (dataclasses/enums). Pure addition.
4. `chore(styles)`: move CSS to `styles/app.css`, add loader, delete dead
   segmented-control CSS. App renders identically.
5. `feat(services)`: `data_access.py` with `as_of` filtering + `freshness.py`.
   Old callers keep working.
6. `feat(services)`: `schedule_cache.py` + `schedules.py` (live → cache → status),
   with `@st.cache_data` TTL. New `schedule_cache` table.
7. `feat(leagues)`: `base.py` Protocol/registry + `mlb/` adapter (schedule, teams,
   opportunities with `mode`). MLB team logic leaves `app.py`.
8. `feat(leagues)`: `wnba/` and `world_cup/` adapters.
9. `feat(services)`: `snapshots.py` + `snapshots` table + `schema_version` table.
10. `refactor(views)`: `components/*` + `views/today.py` (degraded-mode aware).
11. `refactor(views)`: `views/game.py`.
12. `refactor(app)`: slim `app.py` to config + CSS + router + error boundary; add
    `router.py`. This is the switch-over commit.
13. `chore`: `.streamlit/config.toml`, pin deps, drop `plotly`, `diagnostics.py`.
14. `test`: `tests/` — parser fixtures, team matching, empty states, routing,
    as_of leakage, chronological ordering, snapshot writing.
15. `docs`: update `CLAUDE.md`, `README.md`; add `MIGRATION_NOTES.md`, `TEST_PLAN.md`.

---

## Part 6 — Persistent data & daily-workflow protection

Guarantees for this refactor:

- **No persistent data is moved, renamed, or deleted.** `database/sportshub.db`,
  `data/current/`, `data/archive/`, `data/wnba/`, and `logs/` stay exactly where they
  are. They are gitignored (left on disk, never committed), so no git operation can
  touch them.
- **New tables are additive**: `schedule_cache`, `snapshots`, `schema_version`.
  Existing tables (`plate_appearances`, `players`, `games`, `wnba_games`,
  `wnba_player_game_logs`, `wnba_collection_runs`) are untouched. A guarded migration
  creates the new tables if absent.
- **Daily entry points keep working unchanged in behavior**: `setup.command`,
  `run.command`, `update.command`, `update_only.command`, `update_wnba.command`,
  `morning_update.py`, `import_feed.py`, `collect_wnba.py`. Their public CLIs and the
  `sync_mlb_download` archive/current pipeline are preserved.
- **The app still reads the stable working file** `data/current/mlb_pbp_current.xlsx`
  and the same `database/sportshub.db`.
- **Verified runnable between commits.** The baseline is tagged by commit; any step can
  be reverted independently.

`MIGRATION_NOTES.md` (written at the end) will record exactly what moved and confirm
data integrity.
