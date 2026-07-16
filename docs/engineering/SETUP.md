# Setup & Daily Run

> **Purpose** — Exact one-time installation and the daily data/run workflow (macOS).
> **Audience** — The app owner and any operator running Sports Today locally.
> **Update when** — The setup steps, command files, or daily pipeline change.
> **Related** — [Architecture](ARCHITECTURE.md) · [README](../../README.md) · [Docs index](../README.md)

## Part A — One-time installation

### 1. Put the project somewhere permanent

Unzip the project folder and move `sports_hub_v1_daily` to a stable location.

A simple choice is:

```text
/Users/sme/Documents/sports_hub_v1_daily
```

Do not leave the project inside Downloads, because the daily pipeline searches Downloads for vendor files.

### 2. Open the project folder in Finder

You should see:

- `setup.command`
- `update.command`
- `update_only.command`
- `run.command`
- `app.py`
- `morning_update.py`
- `data`
- `database`
- `logs`
- `src`

### 3. Run setup once

Control-click `setup.command` and choose **Open**.

macOS may display a security confirmation the first time. Choose **Open** again.

This command:

- Creates a local Python virtual environment at `.venv`
- Installs Streamlit, pandas, openpyxl, requests, and other requirements
- Marks the command files as executable

When setup finishes, press any key to close the Terminal window.

## Part B — Load the current MLB data for the first time

### 4. Make sure the dated feed is in Downloads

The current vendor file should exist here:

```text
/Users/sme/Downloads/07-12-2026-mlb-season-pbp-feed.xlsx
```

The file may have a later date. The program will choose the newest valid dated feed automatically.

Your older iCloud copy does not need to be moved manually if the same file has already been downloaded into Downloads. The automated pipeline specifically uses Downloads.

### 5. Run the complete daily update

Control-click `update.command` and choose **Open**.

The program will:

1. Search `/Users/sme/Downloads`.
2. Find the newest file named like:
   `07-12-2026-mlb-season-pbp-feed.xlsx`
3. Archive the original at:
   `data/archive/2026/07-12-2026-mlb-season-pbp-feed.xlsx`
4. Copy it to:
   `data/current/mlb_pbp_current.xlsx`
5. Rebuild:
   `database/sportshub.db`
6. Print plate appearance, game, batter, and pitcher counts.
7. Launch Sports Hub in your default browser.

### 6. Verify the files

After the update, confirm these exist:

```text
data/current/mlb_pbp_current.xlsx
data/archive/2026/07-12-2026-mlb-season-pbp-feed.xlsx
database/sportshub.db
logs/mlb_import_history.csv
```

### 7. Verify the app

In the browser:

1. The page title should be **Sports Hub**.
2. The sidebar should show the date through which the imported data runs.
3. Choose the slate date you want to inspect.
4. The app should show:
   - Today's Slate
   - Today's Storylines
   - Ranked 1+ Hit Opportunities
   - Player Explorer
5. Expand an opportunity to see:
   - Opportunity Score
   - Stability Score
   - Supporting evidence
   - Negative evidence
   - Recent game logs

## Part C — Your normal daily workflow

Each day:

1. Download the newest MLB season PBP feed.
2. Leave it in Downloads with its vendor filename.
3. Double-click `update.command`.
4. Use the app when the browser opens.

You do not need to rename, copy, or delete anything manually.

The pipeline keeps all dated source files in the archive and always gives the app the stable working name:

`mlb_pbp_current.xlsx`

## Other commands

### Launch without refreshing data

Double-click:

`run.command`

Use this when the database is already current.

### Refresh data without opening the app

Double-click:

`update_only.command`

### Run through Terminal

From the project folder:

```bash
source .venv/bin/activate
python morning_update.py
```

Update without launching:

```bash
python morning_update.py --no-launch
```

Use a different Downloads folder:

```bash
python morning_update.py --downloads "/some/other/folder"
```

Force the newest file to be recopied:

```bash
python morning_update.py --force
```

## Troubleshooting

### “No dated MLB play-by-play workbook found”

Confirm the file is directly inside:

```text
/Users/sme/Downloads
```

and named like:

```text
07-13-2026-mlb-season-pbp-feed.xlsx
```

### macOS blocks a `.command` file

Control-click the file, choose **Open**, then approve it.

### `python3` is not found

Install a current Python 3 release, then rerun `setup.command`.

### The app says there is no database

Run `update.command` rather than `run.command`.

### The schedule does not load

The imported player data will still work, but live schedule retrieval requires an internet connection.

### The new download is not selected

The embedded date at the beginning of the filename determines recency. Confirm the date is valid and newer than the other dated feeds in Downloads.
