# CLAUDE.md — Sports Hub

## Project purpose

Sports Hub is a personal daily sports-analysis application. Its first supported league is MLB, with WNBA next and eventual support for NBA, NFL, NCAA football, NHL, and World Cup soccer.

This is an **analysis tool**, not an expected-value or sportsbook-price tool. It should:

1. Show the day's games first.
2. Rank the strongest player opportunities across the entire slate, with no forced quota by league.
3. Explain why an opportunity stands out.
4. Show negative evidence just as prominently as supporting evidence.
5. Let the user drill into a game and switch between **Teams** and **Players** analysis.
6. Let the user inspect any player's recent performance and role/opportunity.
7. Preserve daily snapshots so the system can later evaluate which analytical signals were useful.

## Product principles

- Present data and surface opportunity; do not claim certainty.
- Use **Opportunity Score**, not probability, unless a calibrated probability model is explicitly built later.
- A player-market-threshold combination is the atomic opportunity:
  - Juan Soto — 1+ hit
  - Bryce Harper — 2+ total bases
  - Starting pitcher — 6+ strikeouts
- Always distinguish:
  - Performance: what happened recently.
  - Opportunity: how much relevant volume/role is expected today.
  - Threshold fit: how demanding the analyzed threshold is.
- Every recommendation must be explainable.
- Every opportunity must include negative evidence and data-quality/status warnings.
- The app should be willing to say that there are no elite opportunities.
- Do not force a quota by league.
- Avoid a sportsbook visual language. Use a warm, editorial orange theme with off-white backgrounds, white cards, charcoal text, green supporting evidence, and muted red risk evidence.

## Today page hierarchy

1. **Today's Slate**
   - Clickable game cards.
   - Real start time, venue, status, probable starters, and lineup status.
2. **Today's Storylines**
   - Compact, contextual reasons the slate is interesting.
3. **Ranked Opportunities**
   - Compact rows/cards.
   - League emoji filters:
     - 🌎 All
     - ⚾️ MLB
     - 🏀 WNBA
     - ⚽ World Cup
   - Additional filters such as Elite Only and Confirmed Roles.
4. Optional compact previous-day results and model tracking later.

## Game deep dive

The game page should include a concise game snapshot and two primary tabs:

### Teams tab

- Last 5 / 10 / 20 form.
- Home/away performance.
- Runs scored and allowed.
- Offensive and pitching trends.
- Handedness splits.
- Bullpen availability and recent usage.
- Rest, travel, weather, park, and lineup changes.
- Sides and total analysis expressed as competing evidence, not unsupported picks.

### Players tab

- Ranked opportunities for players in this game.
- Projected or confirmed role.
- Expected plate appearances or innings/batters faced.
- Last 5 / 10 / 20 games and last 25 / 50 / 100 plate appearances.
- Relevant handedness and matchup context.
- Threshold histories.
- Supporting and negative evidence.
- Click-through player details.

## Current MLB data

The purchased feed is a season-to-date Excel workbook with approximately one row per completed plate appearance. It uses a two-row header. Important fields include:

- Game ID and date
- Inning and score
- Batting and pitching teams
- Batter/pitcher names and MLB IDs
- Batter/pitcher handedness
- Base-runner state
- Pitch sequence and sequence length
- Hit type
- Play type
- Runs, outs, steals, and description

The current working workbook is always:

`data/current/mlb_pbp_current.xlsx`

Vendor downloads use names like:

`07-12-2026-mlb-season-pbp-feed.xlsx`

The daily pipeline searches `~/Downloads`, selects the newest valid dated file, archives it under:

`data/archive/<YEAR>/`

and copies it to the stable current filename above.

## Current architecture

Reorganized in the architecture cleanup (see `ARCHITECTURE_AUDIT.md` and
`MIGRATION_NOTES.md`). `app.py` is a thin shell; rendering, scoring, and
league logic live in dedicated packages. Leagues are added by implementing the
`LeagueAdapter` protocol and registering — no edits to the Today page.

```text
sports_hub_v1_daily/
├── app.py                  # config, CSS, migration, router dispatch, error boundary
├── router.py               # query-param NavState; Today vs Game dispatch (same tab)
├── domain/models.py        # SlateGame, Opportunity, Evidence, DataStatus, enums
├── leagues/
│   ├── base.py             # LeagueAdapter Protocol + registry
│   ├── mlb/                # teams.py, adapter.py
│   ├── wnba/adapter.py
│   └── world_cup/adapter.py
├── services/
│   ├── data_access.py      # leakage-safe loads (as_of)
│   ├── schedules.py        # live -> cached -> error/empty ordering
│   ├── schedule_cache.py   # SQLite schedule cache
│   ├── snapshots.py        # daily opportunity snapshots
│   ├── migrations.py       # additive schema setup (schema_version)
│   ├── freshness.py        # data-through dates
│   └── app_cache.py        # st.cache_data layer (schedules/opportunities)
├── views/                  # today.py, game.py
├── components/             # date_switch, league_filters, game_cards,
│                           #   opportunity_feed, status_chip, empty_states, ...
├── styles/app.css          # single stylesheet (loaded once)
├── diagnostics.py          # CLI data diagnostics (not part of UI)
├── .streamlit/config.toml  # theme + server settings
├── tests/                  # offline pytest suite
├── morning_update.py  import_feed.py  collect_wnba.py
├── setup.command  update.command  update_only.command  run.command  update_wnba.command
├── data/ (current/ archive/ incoming/ wnba/)   database/sportshub.db   logs/
├── scripts/sync_mlb_download.py
└── src/                    # config, ingest, metrics, mlb_api, wnba_api,
                            #   wnba_collector, opportunity, wnba_opportunity, ...
```

Database tables: `plate_appearances`, `players`, `games`, `wnba_games`,
`wnba_player_game_logs`, `wnba_collection_runs` (existing), plus additive
`schedule_cache`, `opportunity_snapshots`, `schema_version`.

## Daily workflow

The intended user workflow is:

1. Download the latest dated MLB PBP workbook into `~/Downloads`.
2. Double-click `update.command`.
3. The program:
   - Selects the newest valid vendor feed.
   - Compares it to the working file by SHA-256 hash.
   - Archives a copy.
   - Atomically replaces `data/current/mlb_pbp_current.xlsx`.
   - Rebuilds SQLite.
   - Launches Streamlit.
4. If the downloaded file has not changed, the pipeline logs `NO_CHANGE` and still rebuilds/launches safely.

## V1 analytical scope

Initial supported market:

- MLB batter 1+ hit

Current score inputs are intentionally transparent and simple:

- Last 25 PA hit rate
- Last 50 PA hit rate
- Reached-base rate
- Strikeout rate
- Pitches per plate appearance
- Recent PA per game
- Recent improvement/decline
- Current-season sample stability

Near-term additions:

1. Probable starter and pitcher handedness.
2. Batter results versus pitcher hand.
3. Projected and confirmed batting orders.
4. Expected plate appearances.
5. Park and weather.
6. Bullpen freshness.
7. 2+ total bases.
8. Pitcher strikeouts.
9. Dedicated game and player pages.
10. Daily opportunity snapshots and final result tracking.

## Coding standards

- Python 3.11+.
- Prefer `pathlib.Path`.
- Type-hint public functions.
- Fail clearly when required files or columns are missing.
- Do not silently invent or impute critical baseball facts.
- Preserve MLB IDs and game IDs; do not rely on names as join keys.
- Keep data ingestion separate from analytical scoring and UI rendering.
- Avoid opaque model scores in V1.
- Every score component should be inspectable.
- Add tests when changing ingestion, result classification, or scoring logic.
- Do not hardcode the user's absolute Mac path.
- Default Downloads path must be `Path.home() / "Downloads"`.

## Known limitations

- Current season only.
- Plate-appearance grain, not pitch-level Statcast.
- No exit velocity, launch angle, pitch type, velocity, barrels, or expected stats from this purchased file.
- The feed is season-to-date and must be replaced daily.
- Schedule/probable starter data requires internet access.
- Current opportunity scoring does not yet include confirmed lineups, opposing starter quality, weather, or park context.
- Do not represent V0.1 scores as predicted hit probabilities.
