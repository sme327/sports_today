# Test Plan

Run: `pip install -r requirements-dev.txt` then `python -m pytest`.
All tests run offline (no network); schedule payloads are stubbed/recorded.

## Tests added (27, all passing)

| File | Covers |
| --- | --- |
| `test_team_matching.py` | MLB canonicalization: names/abbrs/relocations, unknowns/blanks |
| `test_data_access.py` | `as_of` excludes the slate date and later (leakage bound); missing DB → empty |
| `test_schedules.py` | Degraded ordering: live→LIVE(+cache), empty→EMPTY (no fallback), fail→CACHED, fail+no-cache→ERROR |
| `test_schedule_cache.py` | Round-trip serde; empty result not usable; missing DB → None |
| `test_snapshots.py` | Context captured (provenance, cutoff, engine, flags); idempotent per day; empty writes nothing |
| `test_opportunities.py` | Empty/missing-column and no-matching-team inputs return empty frames (no crash) |
| `test_navigation.py` | Same-tab query-param hrefs; back link carries only `day` |
| `test_registry.py` | All three adapters registered in order; satisfy Protocol; deep-dive flags |
| `test_wnba_parser.py` | ESPN boxscore parsing over a recorded-shape payload; stat helpers |

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
- Filter-toggle interaction test via `AppTest` (click a chip → visible set).
- Snapshot review/evaluation once that feature is built.
