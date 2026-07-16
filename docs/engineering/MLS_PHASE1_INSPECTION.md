# MLS Matchup Page — Phase 1 Inspection

> **Purpose** — Read-only inspection of the codebase to plan an MLS matchup page: what's reusable, what data exists, the risks, and the safest build sequence.
> **Audience** — Product owner, engineering contributors, and AI assistants.
> **Update when** — Superseded by Phase 2 decisions, or when the underlying architecture/data findings change.
> **Related** — [Architecture](ARCHITECTURE.md) · [MLB Game Page](MLB_GAME_PAGE.md) · [Decision Log](DECISION_LOG.md) · [Future Endeavors](../product/FUTURE_ENDEAVORS.md) · [Docs index](../README.md)

_Inspection date: 2026-07-16. Verified against the running app and the live SQLite database via read-only queries; inference is marked explicitly. **No code changed during Phase 1.**_

> **Update (2026-07-16, later):** the "there is no WNBA matchup page" finding below
> reflects the state at inspection time. A basketball-designed **WNBA matchup page
> has since shipped** (see [WNBA Game Page](WNBA_GAME_PAGE.md)); for MLS this means
> there are now **two** matchup-page templates to learn from, and the basketball
> analytics pattern (`services/wnba_analytics.py`) confirms the "collect box scores →
> team/season aggregates → page" flow the MLS plan recommends.

---

## 1. Executive Summary

**The codebase is architecturally ready to *begin* an MLS matchup page, but there is essentially zero soccer *data or analysis* infrastructure to build on, and one premise in the brief is incorrect.**

Three verified realities shape everything:

1. **There is no "WNBA matchup page."** Only **MLB** has `supports_deep_dive=True`; WNBA and World Cup have `supports_deep_dive=False` and their game view renders a schedule-only placeholder (`views/game.py`). WNBA's analysis lives only on the homepage opportunity feed. So there is exactly **one** matchup-page template to learn from: **MLB** (`views/mlb_game.py` + `services/mlb_game_page.py` + `services/mlb_analytics.py`).
2. **No soccer domain data exists.** The SQLite DB has MLB (`plate_appearances`, `players`, `games`) and WNBA (`wnba_*`) tables only. **Zero** MLS/soccer tables, matches, players, standings, venues, lineups, injuries, aliases, or logos. World Cup is **schedule-only**: fetched live from ESPN (with a hardcoded fallback) and cached as JSON in `schedule_cache` — never normalized into domain tables.
3. **The architecture itself transfers cleanly.** The router → view-dispatch → cached page-builder → analytics → immutable page model → pure-HTML components pattern (built for MLB) is sport-agnostic and is the right skeleton for MLS. The adapter protocol, `SlateGame`, `DataStatus`, schedule cache, and the design system are reusable.

**Bottom line:** MLS is a *new build on a proven skeleton*, not a re-skin. The real work is a **soccer data pipeline** (collector + tables + repository) that does not exist yet. The page shell, hero, comparison rows, evidence rows, provenance, and navigation are reusable; every soccer *statistic* is net-new.

## 2. Verified Current Architecture

**Entry & routing** (verified by reading + AppTest):
- `app.py` → `main()`: `st.set_page_config`, `load_css()`, `ensure_schema()`, then `router.read_nav()` → dispatch. Top-level `try/except` error boundary.
- `router.py`: `read_nav()` returns `NavState(day, slate_date, league, game_id)`. `NavState.in_game_view` = `bool(game_id and league)`. **Navigation is query-param only** (`?day=&league=&game=`), same-tab — survives refresh and opens cached games.
- `app.py`: `if nav.in_game_view: game.render(nav) else: today.render(nav)`.

**Layers** (matches `docs/engineering/ARCHITECTURE.md`):

```
domain/         models.py (SlateGame, Opportunity, Evidence, DataStatus/SourceStatus, OpportunityMode)
                mlb_game_page.py (MLB page view-models)
leagues/        base.py (LeagueAdapter Protocol + registry) ; mlb/ wnba/ world_cup/ adapters
services/       schedules.py (live->cached->error ordering) ; schedule_cache.py (SQLite JSON cache)
                data_access.py (as_of-bounded loads) ; freshness.py ; snapshots.py ; migrations.py
                app_cache.py (@st.cache_data wrappers) ; mlb_analytics.py ; mlb_game_page.py (builder)
views/          today.py, game.py (dispatcher), mlb_game.py
components/      game_cards, opportunity_feed, mlb_game, icons, format, navigation, date_switch,
                league_filters, status_chip, empty_states
styles/app.css  one token-driven stylesheet ; loaded once via styles.load_css()
src/            ingest, mlb_api, wnba_api, world_cup_api, wnba_collector, opportunity, wnba_opportunity,
                metrics, wnba_game_logs, config
```

**Data flow (MLB matchup, verified):**
`Today card (?league=MLB&game=<gamePk>)` → `views/game.py:render` → `_find_game(league, slate_iso, game_id)` via `app_cache.cached_slate` → `views/mlb_game.py:render(nav, game)` → `app_cache.cached_mlb_game_page(cache_key, game, as_of_iso)` → `services/mlb_game_page.build_mlb_game_page` → `services/mlb_analytics` (pure numeric engine over `data_access.load_plate_appearances(as_of)`) + `src/opportunity.score_hit_opportunities` → immutable `domain/mlb_game_page.MLBGamePage` → `components/mlb_game.*` (pure HTML).

**Caching/refresh (verified):** `cached_slate` TTL 120s; `cached_mlb_game_page` and `cached_opportunities` TTL 900s. Streamlit does not auto-rerun; refresh on interaction or the sidebar "Refresh cached data" button (`st.cache_data.clear()`).

**Charting:** `requirements.txt` = pandas, openpyxl, streamlit, requests. **No Plotly/Altair/matplotlib** (plotly was removed). All visuals are **HTML/CSS + inline SVG** (icons in `components/icons.py`, bars via CSS width, silhouettes via data-URI).

## 3. MLB Matchup Page Findings

**How it works** (fully traced):
- **Entry:** `views/game.py:render` renders the back-link, resolves the `SlateGame` from `cached_slate`, and — only for `league=="MLB"` — delegates to `views/mlb_game.py:render`. (No MLB logic sits in the router; the dispatch is one branch.)
- **Identifier:** MLB `gamePk` (as `game.game_id`), plus `league` and `day` in query params; `as_of = nav.slate_date`.
- **Builder:** `services/mlb_game_page.build_mlb_game_page(game, slate_date, as_of, pa=None)` — deterministic, no generative text; cached on `game_id | as_of | ENGINE_VERSION`.
- **Analytics:** `services/mlb_analytics.py` — `team_metric_table`, `recent_form`, `player_trend_frame`, `pitcher_league_table`, `match_pitcher`, `team_vs_hand`. All `as_of`-bounded (leakage-safe).
- **Models:** `domain/mlb_game_page.py` — `MLBGamePage`, `MLBGameHero`, `MLBTeamIdentity`, `MLBIdentityMetric`, `MLBPlayerTrend`, `MLBKeyMatchup`, `MLBGameShape`, `MLBStoryline` (all frozen dataclasses); reuses shared `Opportunity`/`DataStatus`.
- **Rendering:** `components/mlb_game.py` — `hero_html`, `team_identity_html`, `game_story_html`, `key_matchups_html`, `player_trends_html`, `game_shape_html`, `storylines_html`, `data_context_html`; `_section(title, body, icon)` shell.
- **Logos/colors:** team logos from `SlateGame.away_logo/home_logo` (MLB `mlbstatic` SVG by team id); player headshots built from `img.mlbstatic.../people/{id}`. **No team colors anywhere.**
- **Status/empty/provenance:** hero shows state via Final-score fields; `data_status = DataStatus(source="Plate-appearance feed", status=LIVE, detail=<as_of context line>)`; each section renders empty when data is thin (honest omission).

**Reusable for MLS (structure, sport-agnostic):** the page shell + `_section`, the hero *layout*, team-identity *card layout* (logo + summary + labeled percentile bars + qualitative tiers), key-matchup *rows* (headline + explanation + supporting metrics + confidence + edge), player-trend *cards* (headshot + fallback + windows), game-shape *editorial block*, storyline *rows*, the data-context line, the opportunity feed, and same-tab back navigation.

**MLB-specific — must NOT transfer to soccer:** probable pitchers, `pitcher_league_table`/`match_pitcher`, batting-order and PA-grain analysis, handedness splits (`team_vs_hand`, `batter_hand`/`pitcher_hand`), hitter-vs-pitcher framing, "Starter-driven / Contact-heavy" game-shape labels, and all baseball terminology (innings, TB/PA, RISP-as-PA). These are baked into `mlb_analytics.py` and `mlb_game_page.py`; MLS needs its own analytics + builder.

## 4. WNBA Matchup Page Findings

**There is no WNBA matchup page** (verified: `WNBAAdapter.supports_deep_dive = False`; opening a WNBA game hits the `views/game.py` placeholder "Deeper team and player analysis is not connected yet"). So there is no WNBA rendering, comparison, recent-form, player-card, availability, or lineup implementation to inspect.

**What WNBA *does* have** (reusable *lessons/patterns*, not a page):
- **Player-game-log model:** `wnba_player_game_logs` (per-player per-game box score). This is the **grain MLS should emulate** — one row per player per match with minutes, shooting, etc. Notably it **has a `position` column** (unused in UI) and `started`/`active` flags — a template for soccer positions/starters.
- **Collector pattern:** `src/wnba_collector.py` — ESPN scoreboard (schedule) + summary boxscore (per-game player stats), retries/backoff, upsert-by-conflict, incremental skip of already-collected games, an audit table (`wnba_collection_runs`), CSV mirrors. **This is the closest template for an MLS collector.**
- **Opportunity scoring:** `src/wnba_opportunity.py:score_wnba_opportunities` — role-gated (minutes threshold), recent-vs-baseline, rule-based support/risk strings. Shows how **role/availability filtering** and **team-token matching** work league-agnostically.
- **Loaders:** `src/wnba_game_logs.py` (as_of-bounded queries, recent windows, threshold history).

**Structural lessons that transfer to MLS:** team-vs-team comparison shape (from MLB), recent form (recent-vs-season-baseline pattern), player spotlights, role-based player stats, availability gating, style contrasts, separation of team-level vs player-level analysis.

**Basketball concepts that must NOT transfer:** possessions, offensive/defensive rating, rebounds, basketball assists, rotation-minute expectations, lineup structures. (These live in WNBA scoring, not in a page.)

## 5. Existing Soccer and World Cup Findings

**Verified implementation** (`src/world_cup_api.py`):
- **Source:** `GET https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=YYYYMMDD&limit=20`.
- **Parsing:** `_parse_espn(payload)` — pure, testable. Extracts `game_id` (event id), teams (`competitors[].team.displayName/shortDisplayName/abbreviation`), `venue`, kickoff `date`, `round` (`competition.type.abbreviation`), broadcasts, **scores/state/winner/status_detail** (Final-score V1), and logos via `_logo` → `country_flag(abbr)` (`flagcdn.com/w160/<iso>.png`) with a `FLAG_CODES` map.
- **Status mapping:** `_state()` maps ESPN `status.type.state` (pre/in/post) → pre/live/final (identical to WNBA's mapping).
- **Fallback:** hardcoded `FALLBACK_GAMES` for the 2026 bracket when ESPN is empty/errors (dicts lack scores → render pre).
- **Caching:** none in the module; the generic `services/schedule_cache.py` caches the normalized `SlateGame` list as JSON (verified: 57 World Cup cache rows).
- **No soccer domain models, no persistence, no knockout-aggregate/xG/lineup logic.**

**Assessment (partly inference, marked):**
- **The ESPN soccer scoreboard structure supports MLS** — same host, same JSON shape, different competition slug (e.g. `usa.1` for MLS). *Inference from the identical ESPN schema; not yet tested against MLS.*
- **Competition-agnostic parsing:** the entire `_parse_espn` (teams, scores, state, winner, venue) is competition-agnostic. **World-Cup-specific:** `FLAG_CODES`/`country_flag` (national flags, not club logos), `FALLBACK_GAMES`, and `round` semantics.
- **A shared soccer client/parser makes sense** — an ESPN-soccer parser parameterized by competition slug, with per-competition logo strategy (flags for WC, club logos for MLS). **But MLS should still have its own `LeagueAdapter`** (distinct label/emoji/source/`supports_deep_dive=True`, and its own `opportunities`/analysis).
- **Coupling risk:** low today (World Cup is isolated), but if MLS reuses `world_cup_api` directly it would couple the two. Recommend a neutral `src/espn_soccer.py` client that both adapters call, rather than MLS importing World Cup.

## 6. Reusable Component Inventory

| Component | Current Location | Current Sport | Reuse Status | Required Change |
|---|---|---|---|---|
| Page/back navigation (`back_href`, `game_href`, same-tab) | `components/navigation.py` | agnostic | **reuse unchanged** | — |
| Router / `NavState` dispatch | `router.py`, `app.py`, `views/game.py` | agnostic | **reuse with extension** | add `elif league=="MLS": mls_game.render` branch |
| `_section(title, body, icon)` shell | `components/mlb_game.py` | MLB-file but generic | **reuse with extension** | promote to a shared module (both MLB & MLS import) |
| Matchup hero (`hero_html`) | `components/mlb_game.py` | MLB | **soccer-specific replacement** | soccer hero: form W/D/L, comp/round, kickoff, no pitchers |
| Team identity card (logo+summary+bars+tiers) | `components/mlb_game.py` `_identity_card`, `_pct_bar`, `_tier` | MLB | **reuse with extension** | keep layout/bar/tier; feed soccer metrics + team colors |
| Team logos | `SlateGame.*_logo`; `src/*_api._logo` | per-league | **reuse with extension** | MLS club-logo source (ESPN CDN); alias-safe lookup |
| Team colors | *(none — not stored anywhere)* | — | **soccer-specific replacement** | new: color map or provider colors (needed for team-colored bars) |
| Game status / score badges | `components/game_cards.py` (`_status_badge`, `game-state`) | agnostic | **reuse unchanged** | — |
| Update timestamp / provenance line | `mlb_game_page.data_status.detail`; `services/freshness.py` | agnostic | **reuse with extension** | soccer freshness (collected_at, projected label) |
| Comparison row / metric row | `_identity_metric` + `.mlb-metric-row` CSS | MLB | **reuse with extension** | generic team-A-vs-team-B bar; extend for soccer stats |
| Recent-form indicator | MLB `recent_form` (composite) + form pill CSS | MLB | **reuse with extension** | soccer form = W/D/L dots (results), not composite index |
| Player card | `components/opportunity_feed.py` avatar; `mlb_game._trend_card` | MLB/WNBA | **reuse with extension** | reuse merged avatar (headshot+badge); add position/number/availability |
| Storyline / evidence row | `mlb_game.storylines_html`, `key_matchups_html`; `Evidence` dataclass | MLB | **reuse with extension** | reuse row layout; soccer rules feed the strings |
| Empty state | `components/empty_states.py`; per-section omission | agnostic | **reuse unchanged** | — |
| Stale/projected label | *(DataStatus lacks PROJECTED/STALE)* | — | **reuse with extension** | extend `SourceStatus` OR add a per-section availability flag |
| Icon system | `components/icons.py` | agnostic | **reuse with extension** | add soccer marks (goal, card, boot, pitch, save) in same 24x24 style |
| Design tokens / responsive CSS | `styles/app.css` | agnostic | **reuse unchanged** (extend with `.mls-*`) | add MLS section classes; no token change |

**Do not reuse for soccer:** anything pitcher/handedness/PA-based in `mlb_analytics.py`/`mlb_game_page.py`.

## 7. Current Data Inventory

| Data Area | Existing Source | Local Storage | Coverage | MLS Readiness | Gap |
|---|---|---|---|---|---|
| Schedules (all leagues) | MLB StatsAPI; ESPN WNBA/soccer | `schedule_cache` (JSON `SlateGame` list) | live+cached | **Partial** — soccer schedule fetch pattern exists | No MLS competition slug wired; no domain persistence |
| MLB PA / players / games | Purchased Excel -> `src/ingest.py` | `plate_appearances`, `players`, `games` | 113k PA, 2026-03-25->07-12 | N/A | baseball-only |
| WNBA player-game logs | ESPN summary boxscore (`wnba_collector`) | `wnba_player_game_logs`, `wnba_games` | 4,532 rows, 05-02->07-16 | N/A (pattern only) | basketball-only |
| Standings / league position | *(none)* | *(none)* | — | **Missing** | needs new source+table |
| Lineups / availability / injuries | *(none)* | *(none)* | — | **Missing** | needs new source+table |
| Team identity/aliases/colors | code maps (`mlb_api`, `wnba_api` name/abbr->CDN) | *(no table)* | MLB+WNBA only | **Missing for MLS** | no MLS aliases/logos/colors |
| Snapshots | homepage opportunities | `opportunity_snapshots` (32) | MLB+WNBA opps | reuse pattern | MLS not snapshotted |

**Explicit MLS presence check (verified read-only):** MLS matches — **none**. MLS teams — **none**. MLS players — **none**. MLS standings — **none**. MLS venues — **none**. Soccer team-match stats — **none**. Soccer player-match stats — **none**. Soccer lineups — **none**. Soccer injuries/availability — **none**. MLS aliases — **none**. MLS logos — **none**. (Only World Cup *schedule* JSON is cached; no soccer *statistics* anywhere.)

## 8. Database Findings

SQLite `database/sportshub.db` (created/extended by `services/migrations.py`, `SCHEMA_VERSION=1`):

| Table | PK | Key columns | Rows | Date range | Notes / limitations |
|---|---|---|---|---|---|
| `plate_appearances` | none (indexed on game/date/batter/pitcher/teams) | game_id, game_date, batter_id, pitcher_id, is_hit, total_bases, has_risp, batter_hand, pitcher_hand… | 113,056 | 2026-03-25->07-12 | MLB PA grain; current season only; no Statcast |
| `players` | player_id | player_id, player_name | 1,301 | — | MLB batters+pitchers, derived |
| `games` | none | game_id, game_date, road_team, scores | 1,444 | — | MLB derived; `road_team="first batting_team"` (fragile), **unused by app** |
| `wnba_player_game_logs` | (game_id, player_id) | minutes, points, rebounds, assists, **position**, started, active, headshot, team_id/abbr | 4,532 | 2026-05-02->07-15 | best template for soccer player-match grain |
| `wnba_games` | game_id | teams, scores, status, is_completed, venue | 188 | 2026-05-02->07-16 | |
| `wnba_collection_runs` | run_id | audit of each collection | 2 | — | collector audit pattern |
| `schedule_cache` | (league, slate_date, fetched_at) | source, status, game_count, payload(JSON) | 176 (MLB 62 / WNBA 57 / WC 57) | — | schedules cached as normalized `SlateGame` JSON; **only place soccer data lives** |
| `opportunity_snapshots` | (snapshot_date, captured_on, league, player_id, market) | scores, evidence(JSON), engine_version, availability flags | 32 | — | daily opportunity provenance |
| `schema_version` | id=1 | version, applied_at | 1 | — | additive migration marker |

**Schema is sound but has no soccer surface.** MLS will need new additive tables (proposed §9): no existing table can hold matches/standings/lineups/player-match stats.

## 9. MLS Domain Model Recommendation

New models live in **`domain/mls_game_page.py`** (mirroring `domain/mlb_game_page.py`), reusing shared `DataStatus` and (optionally) `Opportunity`/`Evidence`. Illustrative shapes only (not to be built now):

```python
# domain/mls_game_page.py  (illustrative)
@dataclass(frozen=True)
class MLSTeamProfile:      # season + splits
    team: str; logo_url: str | None; primary_color: str | None
    record: str            # "W-D-L" points
    form: tuple[str, ...]  # ("W","D","L","W","W") last 5
    conference_rank: int | None; league_rank: int | None
    metrics: tuple["MLSMetric", ...]   # goals / xG-if-available / possession / shots / discipline
    home_split: "MLSSplit"; away_split: "MLSSplit"
    identity_summary: str; sample_context: str

@dataclass(frozen=True)
class MLSMetric:           # parallels MLBIdentityMetric
    name: str; raw_value: float; display_value: str
    league_rank: int | None; percentile: float | None; evidence_text: str; sample_note: str | None

@dataclass(frozen=True)
class MLSMatchHero:
    home_team, away_team, logos, kickoff, venue, competition, round
    home_form, away_form: tuple[str, ...]; state: str; status_detail: str | None

@dataclass(frozen=True)
class MLSPlayerSpotlight:  # reuse merged-avatar renderer
    player_id, name, team, headshot_url, position, number
    availability: str      # projected | confirmed | questionable | suspended | intl_duty | out
    summary: str

@dataclass(frozen=True)
class MLSKeyStoryline / MLSMatchup: title, explanation, supporting_facts, confidence, availability_note

@dataclass(frozen=True)
class MLSGamePage: hero, home_profile, away_profile, key_storylines,
                   spotlights, lineups, data_status, generated_at, as_of
```

Relationship: **compose** existing `DataStatus`; **mirror** the MLB page-model pattern; **do not** overload MLB models.

## 10. Proposed MLS Data Flow (matches current architecture)

```
ESPN soccer scoreboard/summary (usa.1)         <- provider (schedule + boxscore/lineups)
        + a standings source (TBD)
        |
        v
src/mls_collector.py (pattern of src/wnba_collector.py: retries, upsert, audit, incremental)
        |
        v
new additive SQLite tables (mls_teams, mls_matches, mls_team_match_stats,
        mls_player_match_stats, mls_standings, mls_lineups) via services/migrations.ensure_schema
        |
        v
services/mls_repository.py (as_of-bounded reads, a la services/data_access + src/wnba_game_logs)
        |
        v
services/mls_analytics.py (pure numeric: form, splits, attacking/discipline profiles)
        |
        v
services/mls_game_page.build_mls_game_page (deterministic builder; cached like cached_mlb_game_page)
        |
        v
domain/mls_game_page.MLSGamePage (immutable view-model)
        |
        v
views/mls_game.py -> components/mls_game.py (+ shared components) — pure HTML
```

Schedule fetch reuses `services/schedules.get_slate` + `schedule_cache` unchanged (via an `MLSAdapter.fetch_schedule`).

## 11. UI Implementation Assessment

| Section | Classification | Notes / method |
|---|---|---|
| Hero | **new UI work only** | soccer hero (form dots, competition/round) from schedule data + collected form; HTML/CSS |
| Tabs | **buildable with current components** | Streamlit `st.tabs` already styled in `app.css` |
| Matchup snapshot (team vs team) | **requires new collected data** | reuse comparison-bar layout; needs team season stats |
| Recent form (W/D/L) | **requires new collected data** | new W/D/L dot renderer (HTML/CSS); needs results |
| League/conference position | **requires new collected data** | needs a standings source+table (none today) |
| Key storylines | **buildable with new UI work only** (once stats exist) | reuse storyline rows; rules in `mls_analytics`/builder |
| Projected lineups | **requires new collected data** | needs lineup source + a **pitch/formation renderer** (see below) |
| Players to watch | **buildable with current components** (reuse merged avatar) | needs player-match stats for substance |
| Attacking profile | **requires new collected data** | shots, goals, chances; bars/CSS |
| Shooting efficiency | **requires new collected data** (xG = **future/aspirational**) | goals/shots now; xG needs advanced provider |
| Discipline | **requires new collected data** | yellows/reds/fouls; simple stat rows |
| Honest gaps | **buildable with current components** | reuse `data_context` + empty states + availability labels |

**Pitch/formation diagram (recommended method):** **HTML/CSS + inline SVG**, not a charting library (none installed; the whole app is HTML/CSS/SVG). A CSS-grid pitch (green gradient + SVG lines) with absolutely-positioned player tokens (reusing the merged-avatar token) is the lowest-risk, responsive approach and matches the design system. Plotly is not available and shouldn't be added for one diagram. **Comparison bars:** extend the existing `.mlb-bar`/`_pct_bar` CSS (rename to a shared `.stat-bar`), colored with team colors. **Small screens:** reuse the existing `@media (max-width:860px/650px)` stacking; team-identity grid already collapses to one column.

## 12. Risks and Constraints

**Architecture risks:** (a) `_section`/hero/comparison helpers currently live *inside* `components/mlb_game.py` — reusing them for MLS means promoting them to a shared module (small refactor, touches MLB — regression risk to the working MLB page). (b) The MLB page is the only template; MLS must not import MLB analytics.

**Data risks (largest):** there is **no MLS data at all** — matches, stats, standings, lineups must be collected from scratch; **standings and lineups have no identified source** in-repo; xG requires an advanced provider that doesn't exist here.

**UI risks:** no charting library → the pitch diagram and any radial/donut visuals are hand-built SVG/CSS (more effort, but consistent). Team-colored bars require a **team-color source that doesn't exist**.

**Provider/identifier risks:** ESPN event IDs are provider-specific; MLS has **repeated matchups between the same teams** and **multiple competitions** (MLS regular season, Cup Playoffs, Leagues Cup, U.S. Open Cup, CONCACAF) — the current identity (`game_id` = provider event id + `league` string) works for one provider but has **no competition dimension**; **team-name normalization** is a real risk ("Seattle Sounders FC" vs "Sounders", "LA Galaxy" vs "Los Angeles Galaxy", "St. Louis CITY SC", "CF Montréal" accents) and **no alias table exists**.

**Scope risks:** the mockup implies xG, projected lineups, and standings — all of which need data that isn't collected; attempting them in v1 would stall on data, not UI.

## 13. Recommended Implementation Sequence (safest)

1. **Typed static fixture** — a hand-built `MLSGamePage` (real teams, realistic numbers) to design `views/mls_game.py` + `components/mls_game.py` + CSS with **zero data dependency**. Proves the visual/UX before any pipeline.
2. **MLS page shell + adapter registration** — `MLSAdapter(supports_deep_dive=True)`, `fetch_schedule` via a neutral ESPN-soccer client (`usa.1`), route `league=="MLS"` → `views/mls_game.py`. Cards + navigation work; page renders the fixture.
3. **MLS schedule integration** (live schedule → real hero/cards via existing cache).
4. **Team & match data collection** — `src/mls_collector.py` (WNBA-collector pattern) + additive tables + `mls_repository`. Wire team snapshot + recent form + discipline (data that exists from boxscores).
5. **MLS analytics service** — form, splits, attacking/discipline profiles, storyline rules.
6. **Real-data wiring** — replace fixture with repository/analytics; provenance + honest gaps.
7. **Advanced analytics** — xG/possession *only if* a provider is added (separate decision).
8. **Confirmed lineups + live-state** — lineup source + pitch diagram; ties into Live State V2.

This mirrors the (successful) MLB build order and isolates the highest-risk item (data collection) behind a working shell.

## 14. Files Likely to Change/Create Later (not now)

- **Create:** `leagues/mls/adapter.py`, `leagues/mls/teams.py` (aliases/colors), `domain/mls_game_page.py`, `services/mls_analytics.py`, `services/mls_game_page.py` (builder), `services/mls_repository.py`, `src/mls_collector.py`, `src/espn_soccer.py` (shared soccer client), `views/mls_game.py`, `components/mls_game.py`, `collect_mls.py` + `update_mls.command`, `tests/test_mls_*.py`.
- **Modify:** `leagues/__init__.py` (register MLS), `views/game.py` (add `elif league=="MLS"`), `services/migrations.py` (new tables), `services/app_cache.py` (`cached_mls_game_page`), `components/mlb_game.py` (promote `_section`/bar/tier to a shared module), `components/icons.py` (soccer marks), `styles/app.css` (`.mls-*` + shared `.stat-bar`), `requirements-dev.txt`, and docs (`ARCHITECTURE.md`, `DECISION_LOG.md`, new `docs/engineering/MLS_GAME_PAGE.md`, `ROADMAP`).
- **Possibly extend:** `domain/models.py` `SourceStatus` (add `PARTIAL`/`STALE`/`PROJECTED`) — only if a per-section availability flag proves insufficient.

## 15. Open Decisions (need approval before Phase 2)

1. **Data provider(s):** ESPN soccer for schedule+boxscore (free, consistent with WNBA) — confirm; and **where do standings, lineups, and xG come from?** (no in-repo source).
2. **Competition scope for v1:** MLS regular season only, or include Leagues Cup / playoffs? (affects the identity model).
3. **Match identity model:** add a `competition` dimension + a canonical MLS team-id/alias table now, or defer? (recommend: alias table + competition field from the start).
4. **Team colors source:** static curated map vs provider colors (needed for team-colored bars).
5. **Shared-component refactor:** promote `_section`/bars/tiers out of `components/mlb_game.py` into a shared module (touches MLB) — approve the small regression-risk refactor, or duplicate for MLS.
6. **`DataStatus` extension:** extend `SourceStatus` vs. add page-level availability flags for PROJECTED/PARTIAL/STALE.
7. **v1 exclusions:** confirm xG, confirmed lineups, and standings-position are out of v1 if their sources aren't secured.

## 16. Final Recommendation

**The codebase is ready to begin Phase 2 — but only as a fixture-first UI build (steps 1–2).** The architecture, adapter protocol, schedule/cache path, design system, and the MLB template make the *page* low-risk to start. **The prerequisite gating real data is a soccer data pipeline that does not exist** (collector + tables + repository + identified sources for standings/lineups/xG). Recommend: **approve the static-fixture MLS page shell now**, and in parallel **secure the data-source decisions (§15)** before committing to steps 4+. Do not attempt xG/standings/confirmed-lineups in v1 until their sources exist.

---

## Appendix — Answers to the 30 questions

**Architecture.** (1) Today card → `?league&game` → `router.read_nav` → `views/game.py` → MLB-only branch → `views/mlb_game.py` → `cached_mlb_game_page` → builder → analytics → model → components. (2) shell/`_section`, hero *layout*, identity card, comparison/metric rows, player avatar, storyline/evidence rows, empty states, provenance line, navigation, design tokens. (3) pitcher/handedness/PA/at-bat abstractions and "starter-driven" game-shape labels. (4) `domain/mls_game_page.py`. (5) `services/mls_analytics.py` + `services/mls_game_page.py`. (6) `views/mls_game.py` + `components/mls_game.py`. (7) yes — a shared `src/espn_soccer.py` client, but a separate `MLSAdapter`. (8) **yes, the `LeagueAdapter` protocol is sufficient unchanged** (add `MLSAdapter`, `supports_deep_dive=True`, its own `opportunities`/analysis).

**Data.** (9) none. (10) none (no MLS teams/aliases/logos/colors). (11) schedule only: teams, kickoff, venue, score/state/winner, round, logos-as-flags. (12) club logos, team colors, form, competition/round labels for MLS. (13) all team season/split stats. (14) results for W/D/L form + standings. (15) player-match stats, positions, numbers, headshots. (16) a lineup/availability source (none). (17) shots/goals/chances/possession. (18) cards/fouls. (19) xG/advanced — **no source in repo**.

**UI.** (20) tabs, players-to-watch (avatar), honest-gaps, back-nav. (21) hero, W/D/L dots, comparison bars (team-colored), pitch diagram, attacking/discipline panels. (22) **HTML/CSS + inline SVG pitch** (no Plotly). (23) extend `.mlb-bar`/`_pct_bar` → shared `.stat-bar`, team-colored. (24) reuse existing 860/650px stacking; identity grid already collapses. (25) extend tokens + `_section`/bars (promote to shared); add `.mls-*`; don't duplicate.

**Risk.** (26) only-MLB-template + shared-helper promotion regression. (27) no MLS data + no standings/lineup/xG source. (28) ESPN event-id + missing competition dimension + team-name normalization/aliases. (29) xG, confirmed lineups, standings-position (unless sources secured). (30) fixture → shell → schedule → collection → analytics → wiring → advanced → lineups.

---

**No code changed during Phase 1.**
