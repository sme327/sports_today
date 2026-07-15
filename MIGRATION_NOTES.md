# Migration Notes — Architecture Cleanup

Branch: `refactor/architecture-cleanup`. This pass reorganized the code without
adding new sports, markets, or major UI features. Existing user-facing behavior
is preserved; additions are the degraded-mode fallback, daily snapshots, and
leakage-safe `as_of` handling.

## What moved

| Before | After |
| --- | --- |
| ~745-line inline CSS in `app.py` | `styles/app.css` (dead `stSegmentedControl` rules removed), loaded via `styles.load_css()` |
| `MLB_TEAM_ALIASES` + canonicalization in `app.py` | `leagues/mlb/teams.py` |
| MLB schedule/opportunity glue in `app.py` | `leagues/mlb/adapter.py` |
| WNBA schedule/opportunity glue in `app.py` | `leagues/wnba/adapter.py` |
| World Cup schedule glue in `app.py` | `leagues/world_cup/adapter.py` |
| Inline navigation/date/filter/card/feed HTML in `app.py` | `components/*`, `router.py` |
| Today/Game rendering in `app.py` | `views/today.py`, `views/game.py` |
| Ad-hoc SQLite reads | `services/data_access.py` (with `as_of`), `services/freshness.py` |
| `validate_mlb_feed.py`, `validate_wnba_data.py` | `diagnostics.py` (single CLI) |

`app.py` is now a thin shell: page config, CSS, schema migration, router
dispatch, and a top-level error boundary.

## What changed (behavior)

- **Degraded mode:** if a league's live schedule fails, the most recent *valid
  cached* slate for that date is shown (labeled). Only if neither yields games
  and the failure was an error (not a legitimate empty day) is an explicitly
  labeled **"League-wide profiles — live slate unavailable"** section shown.
- **Leakage safety:** all historical windows load via `as_of` and include only
  rows strictly before the slate date.
- **Daily snapshots:** the day's ranked opportunities are persisted once per day
  with full context (components, evidence, schedule provenance, data cutoff,
  context-availability flags, engine version). No snapshot-review UI yet.
- **Schedule caching:** schedules are cached in-memory (120s) and in SQLite; they
  are no longer re-fetched on every widget interaction.
- `score_hit_opportunities` now returns an empty result on empty/missing-column
  input instead of raising.

## New database tables (additive)

`schedule_cache`, `opportunity_snapshots`, `schema_version`. Created idempotently
by `services.migrations.ensure_schema()` at startup. **Existing tables
(`plate_appearances`, `players`, `games`, `wnba_games`, `wnba_player_game_logs`,
`wnba_collection_runs`) are untouched** — verified: 113,056 plate appearances
preserved across the migration.

## What you must do

- **Nothing for daily use.** `update.command`, `run.command`, `update_only.command`,
  `update_wnba.command`, and `morning_update.py` work unchanged.
- To run tests: `pip install -r requirements-dev.txt` then `python -m pytest`.
- `plotly` was removed from `requirements.txt` (it was unused).
- A project-scoped git repo was initialized in this folder (the previous repo
  root was your home directory, with no commits). Persistent data and `.venv`
  are gitignored — present on disk, never committed.

## Data integrity confirmation

- `database/sportshub.db` was not moved or rebuilt by the refactor; only additive
  tables were created.
- `data/current/`, `data/archive/`, `data/wnba/`, and `logs/` are unchanged and
  gitignored.
- The app still reads `data/current/mlb_pbp_current.xlsx` and the same database.
