# Testing

> **Purpose** — What is tested, how to run it, and what still needs coverage.
> **Audience** — Engineers and AI assistants.
> **Update when** — Tests are added/removed or the test philosophy changes.
> **Related** — [Architecture](ARCHITECTURE.md) · [Decision Log](DECISION_LOG.md) · [Docs index](../README.md)

Run: `pip install -r requirements-dev.txt` then `python -m pytest`.

Scoring changes are **not** covered by the unit suite — they are judged against graded
outcomes with `python -m scripts.backtest_scoring`, which recomputes a candidate on every
graded prop using only pre-slate data. Ship only if it widens the band spread **and**
lifts the top 20%. (batter-hit-v4 failed both and was rejected.)
All tests run offline (no network); schedule payloads are stubbed/recorded.

## Test suites (397 tests, all passing)

| File | Covers |
| --- | --- |
| `test_markets.py` | Market registry: canonical labels (byte-identical to scorer output), round-trip `resolve`, "hits allowed" vs bare "hit" ordering, total-bases display/grade, league-optional resolution, grade rules per direction, `actual_display` units, and prop-type taxonomy back-compat |
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
| `test_competition_context.py` | Season/phase/week/round/neutral-site on `SlateGame`: one phase vocabulary across ESPN + MLB StatsAPI, unknown stays `None` (never defaulted to "regular"), `context_label` composition and competition-name dedup, `notable_context` suppressing ordinary regular-season games, cache rows written before these fields existed still deserializing, and **series position** — the regular season showing who leads while the postseason shows the game number, the standing labelled so it cannot read as a game score, nothing shown before the opener, and **clinch/elimination derived from the series shape alone** — a majority of best-of-N, postseason elimination vs a regular-season set that ends nothing, a decider at level, and silence once the series is already decided (a dead rubber must not claim someone faces elimination) |
| `test_editorial.py` | Editorial signals for prop-less leagues: record parsing incl. ties, the min-sample gate, each signal's trigger, **evenly-bad not outranking evenly-good**, upset setup requiring a genuinely strong favourite, no game scoring meaningfully without an explanation, unknown records scoring 0 with a caveat rather than mid-table, `best_game` returning `None` when nothing qualifies, caveats rendered with the same primitive as evidence, **cross-sport normalisation** (league spread measured from the slate, dominant teams in a tight and a wide league scoring alike, within-league order preserved, too-few-teams not normalised, cross-league claims gated), **home-court earned rather than assumed** (upset setup requires the host to be better at home than their own overall; the home record shown either way; a missing split not vetoing the angle), and a guard that **fails if betting odds ever enter the logic** — checked against the parsed AST so the module stays free to explain in prose why odds are excluded |
| `test_injuries.py` | Availability from the ESPN summary endpoint: Out vs questionable split, lookup **by athlete id** (never name), a record with no id ignored, an empty report explicitly *not* a clean bill of health, and the scorer integration — a player listed Out gets no props at all, a day-to-day player is kept but flagged first, an unlisted player unaffected. **MLB roster availability**: every non-active status counts as out (StatsAPI has no questionable tier), the source's own wording kept as the detail, unavailable batters dropped before scoring, and no availability data changing nothing |
| `test_evidence_quality.py` | **The words next to the number.** Severity scaling (a 1-for-25 slump named, not called "cooled"; an ordinary dip still "cooled"), the WNBA last-5 rule and the removal of its false reassurance, DNP rows not shrinking a window, a traded player not offered for their old team while their form still travels with them, accent-folded pitcher matching, an ambiguous name matching nobody, stale start windows (128 days flagged, a normal rotation not), every offered prop stating its clear rate, and the opposing-starter note — flagged when hittable or stingy, silent when average or thin, with shrinkage stopping a small sample from shouting, and inserted first so the evidence cap cannot truncate it |
| `test_served_vs_scored.py` | The Performance headline measures the advice, not the whole scored output: one shared definition of the curation floor (it was duplicated between the view and grading), an inclusive split, a missing score counting as below the floor, the two populations disjoint and complete, the served tally rendered first with the population labelled rather than hidden, the single-number headline preserved for callers that pass no served tally, and a guard that curation is actually selecting for something |
| `test_calibration.py` | Per-market graded records: a poor market with a real sample flagged, a poor-*looking* market on 21 rows not flagged, healthy markets silent, the note phrased as observed history rather than a forecast (R4 rules out "expected hit rate"), no claim without a database, annotation touching only poor markets and never duplicating |
| `test_layering.py` | **Structural layer guards** (one case per module): `src/` never imports `services`/`views`/`components`/`leagues`/`router`/`app` — including function-local imports, via `ast`; `domain/` stays a pure stdlib-only leaf; `src/` never imports Streamlit. Written against the dependency *direction*, so new modules never require editing it |
| `test_registry.py` | All **eight** adapters (MLB, WNBA, World Cup, MLS, NFL, NHL, NBA, NCAAF) registered in order; satisfy Protocol; deep-dive flags |
| `test_espn_leagues.py` | The shared `ScheduleOnlyESPN` base: the four ESPN schedule-only leagues registered and flagged schedule-only, matchup/rank/logo parsing, round-label variants, NCAAF rank prefix, NFL/NHL league+round mapping |
| `test_reliability.py` | `highest_reachable_over` — the shared reachable-bar selector (highest bar clearing the floor, inclusive floor, none-when-unreachable, empty series) used by the TB, WNBA, batter K/BB, and NFL scorers |
| `test_batter_kbb.py` | Batter strikeout market (walks retired 2026-08-09; the test asserts the retirement contract — no scorer, registry and grading branch preserved): over-only high-whiff pick, low-K batter skipped, patient-hitter walks, registry labels + grading, pill classification prefers `market_key` |
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
