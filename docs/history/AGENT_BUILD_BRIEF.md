> 🗄️ **Historical record.** The original V1 build brief. It describes the
> pre-refactor layout and is superseded by
> [Architecture](../engineering/ARCHITECTURE.md); kept for provenance only.

# Copy/Paste Build Brief for Another Agent

Create or update a local Mac project named `sports_hub_v1_daily` with the exact folder structure and behavior below.

## Goal

Build a local Streamlit V1 of a personal Sports Hub. MLB is the first league. It is an analysis and opportunity-surfacing tool, not an expected-value or odds-pricing tool.

The immediate data source is a daily season-to-date MLB plate-appearance Excel feed. Each new download lands in the user's `~/Downloads` folder with a name such as:

`07-12-2026-mlb-season-pbp-feed.xlsx`

The next day's file begins with the next date.

## Required folder structure

```text
sports_hub_v1_daily/
├── app.py
├── morning_update.py
├── import_feed.py
├── setup.command
├── update.command
├── update_only.command
├── run.command
├── requirements.txt
├── README.md
├── CLAUDE.md
├── AGENT_BUILD_BRIEF.md
├── STEP_BY_STEP.md
├── data/
│   ├── current/
│   ├── archive/
│   │   └── 2026/
│   └── incoming/
├── database/
├── logs/
├── scripts/
│   ├── __init__.py
│   └── sync_mlb_download.py
└── src/
    ├── __init__.py
    ├── config.py
    ├── ingest.py
    ├── metrics.py
    ├── mlb_api.py
    └── opportunity.py
```

## Stable working file

The app must always read:

`data/current/mlb_pbp_current.xlsx`

Do not make the app depend on the dated vendor filename.

## Download synchronization requirements

Write `scripts/sync_mlb_download.py` to:

1. Use `Path.home() / "Downloads"` by default.
2. Find files matching the vendor pattern, especially:
   - `*-mlb-season-pbp-feed.xlsx`
3. Parse the date at the beginning of the filename.
4. Select the newest valid feed by embedded date, using file modification time as a tiebreaker.
5. Compute a SHA-256 hash.
6. If the file is unchanged from the current working workbook:
   - Do not duplicate the archive.
   - Log `NO_CHANGE`.
7. Otherwise:
   - Archive the original dated file at `data/archive/<YEAR>/<ORIGINAL_FILENAME>`.
   - Copy it atomically to `data/current/mlb_pbp_current.xlsx`.
   - Never delete the file from Downloads automatically.
8. Write an import history CSV at `logs/mlb_import_history.csv`.
9. Return useful errors when Downloads or the expected file is missing.

## Morning pipeline requirements

Write `morning_update.py` to:

1. Run download synchronization.
2. Import `data/current/mlb_pbp_current.xlsx`.
3. Rebuild `database/sportshub.db`.
4. Print row/game/batter/pitcher counts.
5. Launch Streamlit unless `--no-launch` is supplied.
6. Support `--downloads <PATH>` and `--force`.

## Mac command files

- `setup.command`: create `.venv`, install requirements, make command files executable.
- `update.command`: activate `.venv`, run the morning update, and launch the app.
- `update_only.command`: update data/database without launching Streamlit.
- `run.command`: launch the app using the already-built database.

All command files should use:

`cd "$(dirname "$0")"`

so they work regardless of where the project folder is stored.

## Excel ingestion requirements

The workbook has a two-row header. The second row contains the actual field names. Import it into SQLite with a `plate_appearances` table. Validate fields such as:

- GAME ID
- DATE
- INNING
- BATTING TEAM
- BATTER
- BATTER MLB-ID
- PITCHING TEAM
- PITCHER
- PITCHER MLB-ID
- PLAY TYPE

Preserve MLB IDs and derive transparent fields:

- is_hit
- total_bases
- is_walk
- is_hbp
- is_strikeout
- is_home_run
- is_official_ab
- reached_base
- has_risp
- pa_number

Create indexes for game, date, batter, pitcher, and teams.

## V1 UI requirements

Use an orange editorial theme. The homepage order should be:

1. Today's Slate
2. Today's Storylines
3. Ranked Opportunities
4. Player Explorer

Use real MLB schedule data where possible.

Current opportunity market:

- Batter 1+ hit

Show:

- Opportunity Score
- Stability Score
- Supporting evidence
- Negative evidence
- Last 10 game logs

Do not describe Opportunity Score as a probability.

## Acceptance test

The build succeeds when the user can:

1. Download a dated vendor feed into Downloads.
2. Double-click `update.command`.
3. See the dated source archived.
4. See `data/current/mlb_pbp_current.xlsx` created.
5. See `database/sportshub.db` rebuilt.
6. See the orange Streamlit app open.
7. See the imported data-through date and real selected-day MLB slate.
