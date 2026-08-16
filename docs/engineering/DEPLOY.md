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
excludes the local NFL archive and operator tools. Supported live scores refresh from
the browser; the published schedule remains usable if that refresh fails.

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
4. Verify `https://sports.sme327.com` after the command reports success.

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

- A missing daily snapshot remains visibly missing; never reconstruct it after results.
- A collector failure is reported but does not erase previously good data.
- A failed export or broken internal link stops deployment.
- A failed Cloudflare deployment leaves the previous production bundle online.
- Source data, database files, logs, and generated bundles remain outside Git.
