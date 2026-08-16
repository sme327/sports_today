# Django migration

> **Purpose** — Track the incremental replacement of Streamlit with a conventional
> public web application while preserving the existing sports engine and daily feed.

## Strategy

The Django application lives in `web/` and runs alongside `app.py`. Streamlit remains
the complete production reference until every screen reaches parity. The migration does
not fork the analytics: league adapters, scoring, editorial logic, ingestion scripts,
SQLite data, and the Downloads-based morning update remain shared.

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
- Public Daily Results with date navigation, shared filters, search, sorting, market
  summaries, evidence, and 100-row URL pagination
- Public Performance with served-vs-scored headlines, calibration, over/under,
  edge-finder segments, consistency windows, monthly results, and model versions
- MLB matchup pages using the existing analytical model and section renderers; models
  are prewarmed by the morning update and persisted by game/date/engine version

WNBA/MLS matchup pages, the NFL archive, and data-update pages still use Streamlit
until their Django versions are implemented.

## Local run

```bash
source .venv/bin/activate
python manage.py runserver
```

The existing daily workflow is unchanged:

```bash
python -m scripts.morning_update --no-launch
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
