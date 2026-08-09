# Testing

> **Purpose** — What is tested, how to run it, and what still needs coverage.
> **Audience** — Engineers and AI assistants.
> **Update when** — Tests are added/removed or the test philosophy changes.
> **Related** — [Architecture](ARCHITECTURE.md) · [Decision Log](DECISION_LOG.md) · [Docs index](../README.md)

Run: `pip install -r requirements-dev.txt` then `python -m pytest`.
All tests run offline (no network); schedule payloads are stubbed/recorded.

## Test suites (279 tests, all passing)

| File | Covers |
| --- | --- |
| `test_markets.py` | Market registry: canonical labels (byte-identical to scorer output), round-trip `resolve`, "hits allowed" vs bare "hit" ordering, total-bases display/grade, league-optional resolution, grade rules per direction, `actual_display` units, and prop-type taxonomy back-compat |
| `test_tb_opportunity.py` | Total-bases scorer: impressiveness-weighted threshold pick, min-games gate, shared lineup overlay (confirmed slot evidence + bench cap), empty/missing-column guards |
| `test_data_store.py` | Durable DB store: unconfigured = no-op, `is_configured` needs all keys, download writes the file, `ensure_db_available` skips when present / fetches when missing, publish uploads (fake S3 client, no network) |
| `test_auth.py` | Password gate: constant-time match; no-password bypass returns before any Streamlit call |
| `test_update_pipeline.py` | Shared rebuild pipeline: MLB-only vs. with collectors, collector failures captured non-fatally, publish reflects config (all faked) |
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
| `test_layering.py` | **Structural layer guards** (one case per module): `src/` never imports `services`/`views`/`components`/`leagues`/`router`/`app` — including function-local imports, via `ast`; `domain/` stays a pure stdlib-only leaf; `src/` never imports Streamlit. Written against the dependency *direction*, so new modules never require editing it |
| `test_registry.py` | All **eight** adapters (MLB, WNBA, World Cup, MLS, NFL, NHL, NBA, NCAAF) registered in order; satisfy Protocol; deep-dive flags |
| `test_espn_leagues.py` | The shared `ScheduleOnlyESPN` base: the four ESPN schedule-only leagues registered and flagged schedule-only, matchup/rank/logo parsing, round-label variants, NCAAF rank prefix, NFL/NHL league+round mapping |
| `test_reliability.py` | `highest_reachable_over` — the shared reachable-bar selector (highest bar clearing the floor, inclusive floor, none-when-unreachable, empty series) used by the TB, WNBA, batter K/BB, and NFL scorers |
| `test_batter_kbb.py` | Batter strikeout + walk markets: over-only high-whiff pick, low-K batter skipped, patient-hitter walks, registry labels + grading, pill classification prefers `market_key` |
| `test_results_view.py` | Daily Results rendering: record + not-graded summary, market-table sort/select, recommendation-vs-actual disambiguation, void reason, each filter dimension and combined |
| `test_nfl_ingest.py` | Big Data Ball header flattening (2-row team feed, 3-row player feed) into unique names, opponent pairing, **additive-per-season** writes, and all tables written on import |
| `test_nfl_analytics.py` | Defense-by-pairing (allowed = the opponent's offense), season profiles + league percentiles, battlefields pairing offense vs defense, player-frame types/filters, **`rest_days`** (normal week / short week / off a bye, opener → `None` never 0, other teams' games ignored, unparseable date → `None`) |
| `test_nfl_opportunity.py` | NFL reachable-bar props: highest reachable bar, min-games gate, none when no bar is reachable, `key_players` picks QB/lead RB/receivers |
| `test_nfl_game_page.py` | NFL matchup page: leakage-safe build (records/identity/battlefields from prior games only), rest days, synthesized thesis, small-sample note, season opener empty, archive week/game listing, missing game → `None`. **Player spotlights**: the pick backtested hit/miss against the previewed game, the pick population proven to exclude that game (support reports 5 prior games and their mean — leaking makes it 6), and a player who didn't appear shown with **no result** rather than a miss |
| `test_wnba_parser.py` | ESPN boxscore parsing over a recorded-shape payload; stat helpers |
| `test_wnba_game_page.py` | WNBA matchup page: synthetic box scores, team/opponent pairing, identity labels, battlefields, trends, leakage-safe builds, component rendering |
| `test_mlb_game_page.py` | MLB game page (Phase 1): `as_of` leakage, page builds (with/without probable pitchers), pitcher matching, trend min-sample, no hot/cold overlap, matchups cite real metrics, no unsupported metrics emitted, empty-opportunity state, headshot fallback, component rendering, and a deterministic hot/cold regression on synthetic data |
| `test_mls_game_page.py` | MLS page fallback (no team data): honesty invariants — no fabricated stats/players/formations/tactical leans; ESPN-record/form storylines; hero real; rendering |
| `test_mls_phase3b.py` | MLS team-data integration: provider parsing (reordered/missing/valid-zero), standings, collector retries/idempotency/duplicate-prevention/ID-reconciliation, **leakage-safe repository** (date bound + selected-match exclusion + home/away splits + last-5 + league averages), tactical proxy selection + **banned-tactical-wording** honesty, storyline triggers/dedup/three-empty-states, snapshot/attacking/discipline suppression, **no metric duplicated across sections**, per-match penalty rule, red-card sample-size note |

## Manual verification performed

- `AppTest` renders Today, Tomorrow, WNBA game, and World Cup game with no
  exceptions; opportunity feed and schedule grid present. (The status chip this
  originally checked was retired — freshness now renders in the sidebar via
  `services/freshness.get_freshness`.)
- Snapshots persisted for today (WNBA) and tomorrow (MLB + WNBA) with engine
  versions.
- Migration verified non-destructive on the real DB (113,056 PA rows preserved).
- `scripts/diagnostics.py` reports 30 MLB teams / 1,444 games and 16 WNBA teams / 187 games.

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
- `src/nfl_ingest.py` against a recorded Big Data Ball header shape (schema-drift
  guard). The flattener is covered on synthetic headers, but a vendor layout change
  would land silently.
- NFL archive `AppTest` (`?view=nfl` week browsing → open a matchup), the one NFL
  surface currently verified only by its builder.
