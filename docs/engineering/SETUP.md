# Setup & Daily Run

> **Purpose** — Exact one-time installation and the daily data/run workflow (macOS).
> **Audience** — The app owner and any operator running Sports Today locally.
> **Update when** — The setup steps, command files, or daily pipeline change.
> **Related** — [Architecture](ARCHITECTURE.md) · [README](../../README.md) · [Docs index](../README.md)

## Current public workflow

The public site is a static Cloudflare Pages deployment. The Mac is needed only while
updating and publishing; it does not need to stay on to serve the site.

Normal operator steps:

1. Manually download the newest gated MLB workbook and leave it in `~/Downloads`.
2. Double-click `update_and_publish.command`.
3. Wait for the data update, prediction snapshots, grading, static page build, link
   audit, and Cloudflare publish to complete.
4. Open `sports.sme327.com` on any device. The published snapshot remains available
   after the Mac is turned off; supported live scores refresh in the browser.

`update.command` and `update_and_publish.command` now do the same thing — update
**and** publish. (The data-only variant once let the shortest-named command leave
the published site a day behind.) To refresh local data without publishing, run
`python -m scripts.morning_update` from a terminal.

### One-click launcher (Dock / Desktop)

`Update Sports Today.app` in the project root is a launcher for step 2: it opens a
Terminal window running `update.command`, so the whole run stays visible. Drag it to
the **Dock** (a Dock tile is a path reference — the app itself stays in the project),
or keep the **Desktop alias** at `~/Desktop/Update Sports Today.app`.

Two things it does that a bare double-click does not:

- **It resolves the project root relative to its own bundle**, so no user path is baked
  in. Moving the `.app` out of the project folder breaks it *loudly* — an alert saying
  where it looked — rather than silently updating nothing. Put an alias elsewhere; keep
  the app here.
- **It refuses to start a second concurrent run.** Two updates would fight over the same
  SQLite database and the atomic workbook swap; if one is already going it says so and
  points at the open Terminal window.

The bundle is deliberately **unsigned**. Its executable is a shell script, not a Mach-O
binary, so macOS does not require a signature — and an ad-hoc one would only turn a later
edit of that script into a broken-signature launch failure. Change the icon by
regenerating `Contents/Resources/AppIcon.icns` from `icons/sports-today-1024-master.png`
with `sips` + `iconutil`; edit the launcher itself in place.

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
- `update_and_publish.command`
- `manage.py`
- `scripts/` (`morning_update.py`, `collect_wnba.py`, `diagnostics.py`, `import_feed.py`,
  `import_nfl_feed.py`, `import_boxscore_feed.py`, `sync_mlb_download.py`)
- `data`
- `database`
- `logs`
- `src`

### 3. Run setup once

Control-click `setup.command` and choose **Open**.

macOS may display a security confirmation the first time. Choose **Open** again.

This command:

- Creates a local Python virtual environment at `.venv`
- Installs Django, pandas, openpyxl, requests, and other requirements
- Marks the command files as executable

When setup finishes, press any key to close the Terminal window.

## Part B — Load the current MLB data for the first time

### 4. Make sure the dated feed is in Downloads

The current vendor file should exist here:

```text
~/Downloads/07-12-2026-mlb-season-pbp-feed.xlsx
```

The file may have a later date. The program will choose the newest valid dated feed automatically.

Your older iCloud copy does not need to be moved manually if the same file has already been downloaded into Downloads. The automated pipeline specifically uses Downloads.

### 5. Run the complete daily update

Control-click `update.command` and choose **Open**.

The program will:

1. Search `~/Downloads`.
2. Find the newest file named like:
   `07-12-2026-mlb-season-pbp-feed.xlsx`
3. Archive the original at:
   `data/archive/2026/07-12-2026-mlb-season-pbp-feed.xlsx`
4. Copy it to:
   `data/current/mlb_pbp_current.xlsx`
5. Rebuild:
   `database/sportshub.db`
6. Print plate appearance, game, batter, and pitcher counts.
7. Collect the latest **WNBA** game logs and **MLS** team stats + standings
   (internet required; each is non-fatal — a failure prints a notice and the
   update continues), re-grade recent slates, and precompute today's and
   tomorrow's feeds.
8. Build the static site, audit its links, publish to Cloudflare Pages, and
   verify the live page serves the fresh build.

Every run also appends its full summary to `logs/update_runs.jsonl`, so a past
morning's outcome is checkable after the terminal window has closed. If the
newest feed in Downloads is older than yesterday, the run warns loudly before
proceeding — that usually means the day's download didn't happen or didn't finish.

To ask whether the last run actually finished — both halves — run:

```bash
python -m scripts.run_status
```

It prints the newest data run and the newest publish, checks the live site against
what was last built, and exits non-zero when the site is not serving the current
slate. Use it whenever a run ends ambiguously; it is the answer to "did that work?"

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

1. The page title should be **Sports Today**.
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
4. Open `sports.sme327.com` on any device when it finishes.

You do not need to rename, copy, or delete anything manually.

The pipeline keeps all dated source files in the archive and always gives the app the stable working name:

`mlb_pbp_current.xlsx`

## Other commands

### Publish without refreshing data

From Terminal:

```bash
python -m scripts.publish_pages
```

Use this when the database is already current — after a code or styling change, say.

### Refresh data without publishing

```bash
python -m scripts.morning_update
```

Neither `.command` file does this. Since 2026-08-20 `update.command` is an alias of
`update_and_publish.command` and both update **and** publish, precisely so the
shortest-named command can never leave the published site a day behind.

### Run through Terminal

From the project folder:

```bash
source .venv/bin/activate
python -m scripts.morning_update
```

Use a different Downloads folder:

```bash
python -m scripts.morning_update --downloads "/some/other/folder"
```

Force the newest file to be recopied:

```bash
python -m scripts.morning_update --force
```

## League data collectors (WNBA, MLS)

MLB comes from the daily vendor workbook above, and NFL from season workbooks (see
below). **WNBA and MLS collect their own history from ESPN** into the same
`database/sportshub.db` (additive tables; the MLB data is never touched). These two run
as part of the daily update but are non-fatal, and require an internet connection. The collected data is **gitignored** — a fresh
clone starts empty and the relevant sections show honest awaiting-data states until a
collector runs.

From the project folder (`source .venv/bin/activate` first):

```bash
# MLS — regular-season team match stats + standings (leakage-safe reads in-app).
python -m src.mls_collector --season 2026 --start 2026-03-07
python -m src.mls_collector --force            # re-collect everything

# WNBA — player game logs (powers the WNBA opportunity feed + matchup page).
python -m scripts.collect_wnba                         # see the script for options
```

The MLS collector is **incremental** (skips already-collected matches), validated
(won't write partial rows), and idempotent. It prints a summary and records each run in
`mls_collection_runs`. Only completed **regular-season** matches are stored (no Leagues
Cup, Open Cup, Concacaf, friendlies, or playoffs). Re-run periodically to pick up new
results.

## NFL season feeds

NFL does **not** collect from ESPN like WNBA/MLS — it loads Big Data Ball season
workbooks, a **team** feed and a **player** feed per season, into `nfl_team_games` /
`nfl_player_games`. Writes are additive per season, so loading a new year leaves the
others alone.

**One-off load** (any location, you name the files):

```bash
python -m scripts.import_nfl_feed --team <team.xlsx> --player <player.xlsx>
python -m scripts.import_nfl_feed          # or auto-detect the newest pair
```

**In season, the daily run picks them up for you.** Drop a
`*nfl-season-team-feed*.xlsx` + `*nfl-season-player-feed*.xlsx` pair in `~/Downloads`
and the next `update.command` imports it. It is:

- **silent** when there is no pair — most days, and the whole offseason;
- **skipped** when the pair is unchanged since the last import (fingerprinted by
  name/size/mtime, so a ~9MB player feed is not re-parsed every morning);
- **non-fatal** — a malformed NFL workbook records a note and the MLB update continues;
- **`~/Downloads` only** — deliberately not your documents folder.

Each import is recorded in `nfl_feed_runs`.

**Why it matters:** a live NFL game only opens its deep-dive matchup page if that game's
season is loaded (`services/nfl_bridge.py` joins the two on date + teams). Preseason is
never in the feed, so those cards stay schedule-only by design.

If the vendor changes the workbook layout, the import **fails loudly** and names the
missing columns rather than writing a half-correct table.

## Deployment — Cloudflare Pages

The public site is a **static export**: `scripts/publish_pages` renders every page to
`site-dist/`, audits the internal links, and uploads with `wrangler`. There is no server
and no database in the cloud — the database never leaves this Mac.

```bash
python -m scripts.publish_pages                 # build, audit, deploy
python -m scripts.publish_pages --build-only    # build and audit only
```

**Consequences worth knowing.**

- **Updates come from here.** The Mac builds and pushes; there is no in-app uploader. That
  was a deliberate trade when Streamlit retired — see the Structure Review.
- **The published URL is public.** A static export cannot hold a password gate. Nothing
  personal is in it, but treat the URL as shareable. Cloudflare Access can gate the whole
  project if that changes.
- **Live scores come from the reader's own browser**, not the server. ESPN blocks
  Cloudflare's egress IPs — the identical request returns 200 from this Mac and 403 from a
  Worker — so a server-side fetch silently returns nothing. See the Structure Review §4.
- **Cached pages need recomputing after a scoring or card change.** `schedule_cache` and
  `daily_opportunity_feed` hold rendered output; the site serves those, not live objects.
  `morning_update` refreshes them, but a mid-day change needs
  `python -m django precompute_daily --settings=web.settings` or the fix stays invisible.

## Troubleshooting

### “No dated MLB play-by-play workbook found”

Confirm the file is directly inside:

```text
~/Downloads
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

Run `update.command` (or `update_and_publish.command`) to build one from the day's feed.

### The schedule does not load

The imported player data will still work, but live schedule retrieval requires an internet connection.

### The run stops after "Data updated" and the site is a day behind

The data half and the publish half are separate programs. `morning_update` ends by
printing a line telling you to run `python -m scripts.publish_pages` — and it prints
that **before** `publish_pages` starts. It is the halfway mark, not a success message.
A run that stops there has not published.

The static build takes several minutes and prints nothing until
`Static link audit passed.`, so a silent terminal usually means it is still working.
Rather than guess, ask:

```bash
python -m scripts.run_status
```

`Publish  STARTED ... — NEVER FINISHED` means a publish began and never returned:
either it is still running, or it hung and was killed. A finished run does the live
check itself (`verify_live`) and says `Verified live at ...`.

Publishing needs Node and `npx`, which fetches `wrangler` into the npx cache. That
resolution is forced non-interactive (`npx --yes`); before 2026-08-28 npm could stop
on an `Ok to proceed?` prompt and wait forever with the build already complete and no
error printed.

### The new download is not selected

The embedded date at the beginning of the filename determines recency. Confirm the date is valid and newer than the other dated feeds in Downloads.
