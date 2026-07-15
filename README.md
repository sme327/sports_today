# Sports Hub V1 Daily

A local orange-themed Streamlit sports-analysis app powered by a daily season-to-date MLB plate-appearance workbook.

## One-time setup

1. Move this folder somewhere permanent, outside Downloads.
2. Control-click `setup.command` and choose **Open**.
3. Download the latest vendor feed into `~/Downloads`.
4. Control-click `update.command` and choose **Open**.

See [STEP_BY_STEP.md](STEP_BY_STEP.md) for exact instructions.

## Daily workflow

1. Download the newest file named like:
   `07-13-2026-mlb-season-pbp-feed.xlsx`
2. Leave it in Downloads.
3. Double-click `update.command`.

The pipeline archives the dated source, updates:

`data/current/mlb_pbp_current.xlsx`

rebuilds SQLite, and opens Sports Hub.

## Important files

- `CLAUDE.md`: full project purpose, product principles, architecture, and constraints.
- `AGENT_BUILD_BRIEF.md`: copy/paste directions for another coding agent.
- `STEP_BY_STEP.md`: exact Mac installation and daily usage.
- `morning_update.py`: complete daily pipeline.
- `scripts/sync_mlb_download.py`: finds, archives, and renames the latest feed.

## Current navigation model

- **Today** is intentionally simple: league toggles, game cards, and the top five MLB opportunities.
- Click any game card to open its game view.
- MLB game views contain **Teams** and **Players** tabs.
- WNBA cards currently open a schedule-only placeholder until a WNBA analysis feed is connected.
- League buttons are independent toggles. When neither is selected, every supported sport with games that day is shown.
