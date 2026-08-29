# Deploy — Cloudflare Pages

> **Purpose** — Publish Sports Today for phone, tablet, and computer access without
> an always-on Mac or paid application server.
> **Audience** — The owner/operator.
> **Update when** — Cloudflare project, hostname, build, or update workflow changes.
> **Related** — [Setup](SETUP.md) · [Django Migration](DJANGO_MIGRATION.md) ·
> [Prediction Evaluation](PREDICTION_EVALUATION.md)

## Architecture

Django renders the public routes locally into `site-dist/`. Cloudflare Pages serves
that static bundle at `sports.sme327.com`. The private SQLite database and gated MLB
workbook never leave the Mac. The Mac can be off after a publish.

The public bundle includes Today/Tomorrow, current matchup pages, seven Results dates,
and every supported Performance cohort/period/market/direction view. It deliberately
excludes the local NFL archive and operator tools. MLB, WNBA, MLS, NFL, and NCAAF live
scores refresh from the browser; the published schedule remains usable if that fails.
NCAAF includes FBS plus FCS during August Week Zero, then returns to FBS-only slates.
Week Zero cards intentionally open the simplified schedule-only matchup page as the
football navigation/layout rehearsal, even before records are mature.

## One-time Cloudflare setup

1. Authenticate Wrangler with the Cloudflare account that owns `sme327.com`.
2. Create or select the Pages project named `sports-today`.
3. Attach the custom domain `sports.sme327.com` in the Pages project.
4. Keep the generated `sports-today-clr.pages.dev` address as a diagnostic fallback.

No R2 bucket, database service, Worker, always-on process, or paid plan is required for
the current static architecture.

## Normal publish

1. Download the latest gated MLB workbook to `~/Downloads`.
2. Double-click `update_and_publish.command`.
3. The workflow imports data, updates connected feeds, creates immutable prediction
   snapshots, grades available results, precomputes Today/Tomorrow and matchup pages,
   exports the site, audits every internal link, and deploys to Pages.
4. Verify `https://sports.sme327.com` after the command reports success. The run
   already checks this itself: after deploying it refetches the live page and compares
   its stylesheet hashes and `sports-today-build` stamp against what was just built,
   printing `Verified live at ...`. Absent that line, treat the publish as unconfirmed.

Deploying requires Node and `npx`, which resolves `wrangler` through the npx cache.
There is no `package.json` here pinning it, so the version floats.

## Publishing without a new MLB feed

Double-click `refresh.command`, or:

```bash
python -m scripts.morning_update --skip-mlb
python -m scripts.publish_pages
```

Today's and tomorrow's games come from the schedule sources, not the vendor workbook, so
the published slate can be brought up to date on a morning the file has not arrived.
Schedules, live results, the WNBA/MLS collectors, regrading and both precomputed slates
all run; only the MLB import is skipped, and it is most of a full run's time. MLB props
stay as they were at the last real import.

The ordinary run degrades the same way rather than stopping: a missing workbook warns
and carries on, because the alternative was publishing nothing at all (see Failure
behavior).

## Build and validate without deploying

```bash
source .venv/bin/activate
python -m scripts.publish_pages --build-only
```

The generated `site-dist/` directory is disposable and gitignored. A successful build
prints both the rendered page count and `Static link audit passed.`

## Manual deployment command

```bash
source .venv/bin/activate
python -m scripts.publish_pages
```

The project and branch can be overridden with `SPORTS_TODAY_PAGES_PROJECT` and
`SPORTS_TODAY_PAGES_BRANCH`.

## Failure behavior

- **A missing MLB workbook no longer stops the run.** It used to raise before the
  publish step, and under `set -e` that meant the site kept the previous day's games —
  the worst available outcome, since the slate never needed the workbook. The run now
  warns, skips the import and publishes the day's games against the database as it
  stands.
- A missing daily snapshot remains visibly missing; never reconstruct it after results.
- A collector failure is reported but does not erase previously good data.
- A failed export or broken internal link stops deployment.
- A failed Cloudflare deployment leaves the previous production bundle online, and
  wrangler's non-zero exit is reported last and loudly — it can fail mid-upload after
  the build and link audit have both passed.
- **The deploy cannot block on a prompt.** `npx` is invoked with `--yes`. On
  2026-08-28 a run built all 740 pages, then sat on npm's `Ok to proceed?` question
  at 0% CPU with no error and no timeout while the site served the previous day's
  slate. A hang is worse than a failure here: the failure paths above all leave a
  loud signal, and this one left none.
- **A publish that never finishes is still visible afterwards.** `publish_pages`
  writes a `publish_started` record to `logs/update_runs.jsonl` before it begins and a
  `publish_finished` record when it ends, whatever the outcome. A process that never
  returns cannot log its own failure, so the unmatched start *is* the evidence.
  `python -m scripts.run_status` reads that pair, compares the live build stamp
  against the last one built, and exits non-zero when the site is behind.
- Source data, database files, logs, and generated bundles remain outside Git.
