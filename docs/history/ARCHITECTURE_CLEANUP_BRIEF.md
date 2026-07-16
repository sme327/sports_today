> 🗄️ **Historical record.** The brief that commissioned the architecture
> cleanup. Kept for provenance; the resulting structure and decisions live in
> [Architecture](../engineering/ARCHITECTURE.md) and the
> [Decision Log](../engineering/DECISION_LOG.md).

# Sports Hub Architectural Cleanup — Claude Work Brief

You are taking over an existing local Streamlit sports-analysis application for a focused architectural cleanup.

## First rule

Do **not** add new product features during this pass.

The goal is to make the existing app safer, easier to understand, easier to test, and easier to extend. Preserve current user-facing behavior unless a behavior is clearly broken.

Before changing code:

1. Read `CLAUDE.md`, `README.md`, and the current source tree.
2. Run or inspect the application.
3. Review the SQLite schema and the current MLB/WNBA data flows.
4. Write a brief audit of the current architecture and identify risks or missing considerations.
5. Propose the cleanup plan.
6. Then implement it.

## Product context

Sports Hub is a personal daily sports-analysis application.

Current supported slate display:

- MLB
- WNBA
- World Cup

Current data/analysis:

- MLB season-to-date plate-appearance workbook imported into SQLite
- MLB preliminary 1+ hit opportunity rankings
- WNBA schedule collector
- WNBA completed player-game box-score collector
- WNBA preliminary points, rebounds, and assists opportunity rankings
- Today/Tomorrow date switch
- League filters
- Clickable game cards
- MLB game deep dive with Teams and Players tabs
- WNBA and World Cup game pages are schedule-only for now

This is an analysis tool, not an expected-value or sportsbook-price tool.

Core principles:

- Today's slate comes first.
- Opportunities are ranked without forced league quotas.
- Every opportunity includes supporting and negative evidence.
- Opportunity Score is not a probability.
- The system must be transparent and inspectable.
- Missing or incomplete data should produce honest empty states, not crashes.

## Current problem

The app has grown through repeated patches. `app.py` now handles too many responsibilities:

- Page configuration and CSS
- Session and query-string navigation
- Date controls
- League filters
- Schedule collection
- Game card rendering
- Deep-dive rendering
- Data loading
- MLB team normalization
- MLB opportunity ranking
- WNBA opportunity ranking
- Empty-state messaging
- HTML generation

This has already caused initialization-order errors such as using `wnba_logs` before it was defined.

We want a clean structure before adding more features.

## Required architectural goals

Create a modular structure similar to the following, but adjust it if you have a better reasoned design:

```text
sports-hub/
├── app.py
├── pages/
│   ├── today.py
│   └── game.py
├── components/
│   ├── date_switch.py
│   ├── league_filters.py
│   ├── game_cards.py
│   ├── opportunity_feed.py
│   ├── empty_states.py
│   └── navigation.py
├── services/
│   ├── schedules.py
│   ├── data_access.py
│   └── cache.py
├── leagues/
│   ├── mlb/
│   │   ├── data.py
│   │   ├── normalize.py
│   │   ├── opportunities.py
│   │   └── game_view.py
│   ├── wnba/
│   │   ├── data.py
│   │   ├── opportunities.py
│   │   └── game_view.py
│   └── world_cup/
│       ├── data.py
│       └── game_view.py
├── styles/
│   └── app.css
├── src/
│   └── ingestion and existing lower-level modules as appropriate
├── tests/
│   ├── test_navigation.py
│   ├── test_team_matching.py
│   ├── test_mlb_opportunities.py
│   ├── test_wnba_opportunities.py
│   └── test_empty_states.py
└── .streamlit/
    └── config.toml
```

Do not follow this blindly. Improve it if another organization better fits the application.

## Specific cleanup requirements

### 1. Make `app.py` minimal

`app.py` should mainly:

- configure Streamlit
- initialize state
- load the selected page
- route to Today or Game view
- handle top-level exceptions gracefully

It should not contain large HTML templates, scoring logic, or league-specific normalization dictionaries.

### 2. Centralize state and navigation

Create one clear mechanism for:

- Today/Tomorrow selection
- League filters
- Game selection
- Back navigation
- Query-parameter synchronization

Avoid setting the same widget both through `default=` and session state.

All internal navigation must stay in the same browser tab.

### 3. Separate data loading from rendering

Create explicit functions/services for:

- loading MLB plate appearances
- loading WNBA player game logs
- fetching schedules
- caching each dataset
- checking data freshness
- validating whether required tables exist

No page or component should query SQLite ad hoc.

### 4. Define normalized domain models

Introduce typed structures or dataclasses for concepts such as:

- `SlateGame`
- `Opportunity`
- `Evidence`
- `DataStatus`

The homepage should render a common opportunity model regardless of league.

A common opportunity should include at least:

```python
league
player_id
player_name
team_id
team_name
market
threshold
opportunity_score
stability_score
supporting_evidence
negative_evidence
image_url
data_status
```

### 5. Isolate league-specific logic

MLB and WNBA logic should not be interwoven in the Today page.

Each league adapter should be responsible for:

- schedule normalization
- team identity matching
- player eligibility
- opportunity generation
- league-specific warnings
- game-view support

The Today page should ask each available league adapter for games and opportunities through a consistent interface.

### 6. Improve robustness

Add safe behavior for:

- missing database
- missing table
- empty query result
- no games today
- league has games but no player data
- scheduled team cannot match historical data
- remote schedule endpoint fails
- partial or stale data
- malformed image URL
- opportunity engine produces zero rows

No empty DataFrame should be sorted by columns that do not exist.

No variable should be used before initialization.

### 7. Add validation

At startup or via a diagnostic command, report:

- MLB distinct teams, games, date range, and player count
- WNBA distinct teams, games, date range, player-game rows, and player count
- whether current data is likely complete
- whether scheduled teams can match stored teams

Keep validation separate from normal UI rendering.

### 8. Move CSS out of `app.py`

Put the visual system in a CSS file and load it once.

Preserve the current intended design:

- dark warm canvas
- orange accent
- orange Today/Tomorrow selected state
- joined Today/Tomorrow capsule with angled divider if technically stable
- readable typography
- compact game cards
- team logos
- ranked opportunity feed

Do not spend this pass redesigning the page. Fix only styling defects caused by the refactor.

### 9. Add tests

At minimum, add tests for:

- MLB schedule-to-feed team matching
- WNBA schedule-to-log team matching
- empty opportunity results
- WNBA logs loaded before use
- Today/Tomorrow state
- leagues with no games do not show filter buttons
- chronological slate ordering across leagues
- opportunity results restricted to scheduled teams
- same-tab internal navigation URL generation

Tests should not require internet access. Use fixtures or mocked schedule payloads.

### 10. Preserve daily workflows

These must keep working:

- `setup.command`
- `run.command`
- `update.command`
- `update_wnba.command`
- `morning_update.py`
- MLB download archive/current-file pipeline
- WNBA incremental collection
- `database/sportshub.db`

Do not move or rename persistent data without adding a migration and documenting it.

## Critical review requested

Before implementing, specifically assess whether we are overlooking:

- Streamlit limitations that will continue to create friction
- whether query-parameter navigation is the best approach
- whether league adapters should be classes, protocols, or plain functions
- whether a single SQLite database remains appropriate
- whether raw, derived, and snapshot data need separate tables/databases
- how to store daily opportunity snapshots for future evaluation
- how to avoid data leakage when reviewing historical dates
- how to track data provenance and refresh timestamps
- how to handle player/team identity changes
- how to design for future NBA, NFL, NHL, and NCAA football support
- whether the current opportunity scoring functions need a shared interface
- what should remain Streamlit-specific versus reusable analytics code

Point out problems even when they were not explicitly mentioned.

## Deliverables

Provide:

1. `ARCHITECTURE_AUDIT.md`
   - Current issues
   - Risks
   - Missing considerations
   - Proposed architecture
   - Key decisions and tradeoffs

2. Refactored project code.

3. `MIGRATION_NOTES.md`
   - What moved
   - What changed
   - Anything the user must do
   - Confirmation that persistent data remains intact

4. `TEST_PLAN.md`
   - Tests added
   - Tests still needed

5. Updated `CLAUDE.md` and `README.md`.

6. A short verification checklist showing:
   - Today page loads
   - Tomorrow page loads
   - MLB slate loads
   - WNBA slate loads
   - World Cup slate loads on applicable dates
   - game navigation stays in the same tab
   - MLB opportunities handle missing/incomplete data
   - WNBA opportunities load without initialization errors
   - no relevant Streamlit warnings appear in Terminal

## Working style

- Make a backup or work on a branch/copy before refactoring.
- Prefer small, reviewable commits.
- Do not delete working functionality simply to simplify the architecture.
- Do not add new sports, markets, or visual features in this pass.
- Be candid about anything that cannot be validated.


## UI behavior to preserve from the final pre-refactor polish

- Today/Tomorrow is a custom joined capsule, not a Streamlit segmented widget.
- Selected date uses Sports Hub orange, never Streamlit red.
- The center divider is visibly angled.
- Date links navigate in the same browser tab.
- League controls are independent on/off chips.
- No selected league means show all leagues with games that day.
- Every opportunity row includes:
  - sport emoji
  - team logo or player/team image fallback
  - player name
  - market
  - team name
- The page warning is a compact status chip, not a full-width alert bar.
