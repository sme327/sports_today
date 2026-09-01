# Django migration

> **Purpose** — Track the incremental replacement of Streamlit with a conventional
> public web application while preserving the existing sports engine and daily feed.

## Strategy

The Django application in `web/` is the public renderer. It is exported to static HTML
and hosted by Cloudflare Pages; Streamlit remains only as a local reference/operator
surface. League adapters, scoring, editorial logic, ingestion scripts, SQLite data,
and the Downloads-based morning update remain shared.

## Current milestone

- Public Django site shell and Today/Tomorrow routing
- Existing SQLite database and freshness metadata
- Live/cached league schedules
- League and opportunity filters through query parameters
- Existing game-card and opportunity HTML/CSS
- Health endpoint at `/health/`
- WhiteNoise static-file support and Gunicorn production entry point
- Precomputed daily display feed: visitor requests read SQLite only; schedule APIs and
  Pandas scoring run during the morning update
- Deferred schedule fragment refresh: cached games paint immediately, then stale live
  schedules refresh after first paint with a short anti-stampede lock
- Public Daily Results with seven dated audit views, date status, market summaries,
  evidence, and the complete qualifying prediction list
- Public Performance with All qualifying / Featured / Other qualifying cohorts,
  calibration, over/under, edge-finder segments, consistency windows, monthly results,
  and model versions
- League-wide standings plus an MLB playoff-race view: the current six-team fields,
  Wild Card bubbles, and a factual two-week watch list of consequential games
- MLB player trends for active players only: hit streaks, batter-hit changes,
  multi-strikeout changes, and recent starting-pitcher strikeout pace
- MLB matchup pages using the existing analytical model and section renderers; models
  are prewarmed by the morning update and persisted by game/date/engine version
- WNBA matchup pages using the existing basketball-specific model, snapshots, trends,
  battlefields, and opportunity feed with the same persistent prewarm path
- MLS matchup pages using the existing leakage-safe team analysis, tactical and
  attacking comparisons, storylines, lineups, watch timeline, and honest data-gap
  states; pages use the same versioned persistent cache and morning prewarm path
- The NFL archive and historical deep dives remain available locally but are excluded
  from the public export by product decision.

The data-update/operator workflow remains local on the Mac because the MLB provider is
gated and requires a manual download. The Mac does not need to remain on afterward.

## Zero-cost Cloudflare Pages path

The public Django routes can also be exported as a static Pages deployment. Django
remains the tested rendering engine on the Mac; Cloudflare serves the finished HTML,
CSS, and JavaScript without an always-on Python host or published SQLite database.

```bash
python -m scripts.publish_pages --build-only
```

The export writes `site-dist/`, follows public Today/Tomorrow matchup links plus Results
and every supported Performance filter combination, collects static assets, audits all
internal links, and removes the Django-only deferred HTMX refresh. The generated bundle
is disposable and gitignored; the NFL archive is not crawled or published.

`update_and_publish.command` runs the normal Downloads-based update, builds this static
bundle, and deploys it with Cloudflare Wrangler. The first publish requires a one-time
Cloudflare login and Pages project creation.

Published Today/Tomorrow pages read the same ESPN scoreboards used by the local app
directly from the browser once on load and every 60 seconds while open. ESPN permits
cross-origin browser reads but blocks Cloudflare's server network, so this avoids a
needless Function and keeps static requests outside Worker quotas. Failures are
deliberately silent: the last published schedule remains fully usable. ESPN's
`pre`/`in`/`post` states are normalized to pre/live/final in the browser so a live or
final badge replaces the scheduled time. The schedule controls can also hide completed
games without another server request, including games that become final while open.

## Local run

```bash
source .venv/bin/activate
python manage.py runserver
```

The existing daily workflow is unchanged:

```bash
python -m scripts.morning_update
```

That command now builds both today's and tomorrow's public read models. To refresh only
the schedules and public feeds without importing a new workbook:

```bash
python manage.py precompute_daily
```

The homepage returns a `Server-Timing` header with `schedule`, `feed`, and total `app`
durations so cold-read performance remains observable.

## Production command

```bash
gunicorn web.wsgi:application --bind 0.0.0.0:${PORT:-8000}
```

Required production environment:

- `SPORTS_TODAY_SECRET_KEY` — a long random value
- `SPORTS_TODAY_DEBUG=0`
- `SPORTS_TODAY_ALLOWED_HOSTS=sports.sme327.com,<provider-hostname>`
- `SPORTS_TODAY_SECURE_SSL=1` when the host forwards HTTPS correctly

The initial deployment needs persistent storage containing `database/sportshub.db`.
SQLite remains the migration database until operational evidence justifies PostgreSQL.
