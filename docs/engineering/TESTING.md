# Testing

> **Purpose** — What is tested, how to run it, and what still needs coverage.
> **Audience** — Engineers and AI assistants.
> **Update when** — Tests are added/removed or the test philosophy changes.
> **Related** — [Architecture](ARCHITECTURE.md) · [Decision Log](DECISION_LOG.md) · [Docs index](../README.md)

Run: `pip install -r requirements-dev.txt` then `python -m pytest`.
All tests run offline (no network); schedule payloads are stubbed/recorded.

## Test suites (173 tests, all passing)

| File | Covers |
| --- | --- |
| `test_markets.py` | Market registry: canonical labels (byte-identical to scorer output), round-trip `resolve`, "hits allowed" vs bare "hit" ordering, league-optional resolution, grade rules per direction, `actual_display` units, and prop-type taxonomy back-compat |
| `test_team_matching.py` | MLB canonicalization: names/abbrs/relocations, unknowns/blanks |
| `test_data_access.py` | `as_of` excludes the slate date and later (leakage bound); missing DB → empty |
| `test_schedules.py` | Degraded ordering: live→LIVE(+cache), empty→EMPTY (no fallback), fail→CACHED, fail+no-cache→ERROR |
| `test_schedule_cache.py` | Round-trip serde; empty result not usable; missing DB → None |
| `test_snapshots.py` | Context captured (provenance, cutoff, engine, flags); idempotent per day; empty writes nothing |
| `test_opportunities.py` | Empty/missing-column and no-matching-team inputs return empty frames (no crash); **lineup overlay** — confirmed-slot evidence, bench-cap (≤25), honest not-posted state, and backward-compat with no `lineups` arg |
| `test_scores.py` | MLB 1+ hit scorer components, score/stability bounds, support/risk rules |
| `test_pitcher_opportunity.py` | SP props: per-start line extraction (inning `1T`/`1B` parse), opener exclusion, two-directional over/under selection, min-starts gate |
| `test_grading.py` | Prop grading hit/miss/void (incl. DNP=void honesty), idempotency, no-grading-today guard, dedup/min-score reads, summary + **`summarize_by_market`**, row classification, market-breakdown render |
| `test_mlb_trends.py` | MLB trend spotlights: pitcher per-start sparklines/direction/props/min-starts, batter dots/L5-L10-L25 windows/streak/min-games, rendering, empty states |
| `test_deploy_boot.py` | App boots + degrades honestly against an empty DB (cloud-deploy path) |
| `test_navigation.py` | Same-tab query-param hrefs; back link carries only `day` |
| `test_registry.py` | All **four** adapters (MLB, WNBA, World Cup, MLS) registered in order; satisfy Protocol; deep-dive flags |
| `test_wnba_parser.py` | ESPN boxscore parsing over a recorded-shape payload; stat helpers |
| `test_wnba_game_page.py` | WNBA matchup page: synthetic box scores, team/opponent pairing, identity labels, battlefields, trends, leakage-safe builds, component rendering |
| `test_mlb_game_page.py` | MLB game page (Phase 1): `as_of` leakage, page builds (with/without probable pitchers), pitcher matching, trend min-sample, no hot/cold overlap, matchups cite real metrics, no unsupported metrics emitted, empty-opportunity state, headshot fallback, component rendering, and a deterministic hot/cold regression on synthetic data |
| `test_mls_game_page.py` | MLS page fallback (no team data): honesty invariants — no fabricated stats/players/formations/tactical leans; ESPN-record/form storylines; hero real; rendering |
| `test_mls_phase3b.py` | MLS team-data integration: provider parsing (reordered/missing/valid-zero), standings, collector retries/idempotency/duplicate-prevention/ID-reconciliation, **leakage-safe repository** (date bound + selected-match exclusion + home/away splits + last-5 + league averages), tactical proxy selection + **banned-tactical-wording** honesty, storyline triggers/dedup/three-empty-states, snapshot/attacking/discipline suppression, **no metric duplicated across sections**, per-match penalty rule, red-card sample-size note |

## Manual verification performed

- `AppTest` renders Today, Tomorrow, WNBA game, and World Cup game with no
  exceptions; opportunity feed, schedule grid, and status chip present.
- Snapshots persisted for today (WNBA) and tomorrow (MLB + WNBA) with engine
  versions.
- Migration verified non-destructive on the real DB (113,056 PA rows preserved).
- `diagnostics.py` reports 30 MLB teams / 1,444 games and 16 WNBA teams / 187 games.

## Tests still worth adding

- MLB game deep-dive `AppTest` on a date with a live MLB slate (today's feed
  returned none, so this path was verified only via the unchanged scoring
  functions and Tomorrow's snapshot).
- Recorded full ESPN/StatsAPI schedule payloads → adapter `fetch_schedule`
  (schema-drift regression guard).
- Filter-toggle interaction test via `AppTest` (click a chip → visible set), incl.
  the Results view's threshold band + prop-type sub-filter.
- `src/mlb_lineups.py` payload parsing over a recorded StatsAPI `lineups` shape
  (schema-drift guard); the scorer overlay is already covered offline via a fixture.
- Results Phase 3 calibration analytics once that feature is built.
