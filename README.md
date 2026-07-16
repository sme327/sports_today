# Sports Today

**A calm daily sports companion — not a dashboard.** Sports Today answers one
question in under a minute: *"What should I pay attention to today?"* It surfaces
the day's games and the strongest, **explainable** player opportunities across
leagues, and it is honest about uncertainty. It is not a sportsbook, a stats
encyclopedia, or a fantasy tool.

> New here? This README gets you oriented in ~10 minutes. The full knowledge base
> is in **[`docs/`](docs/README.md)**.

## Why it exists

Fans don't lack sports information — they lack a way to know *what deserves
attention today*. Sports Today curates: it shows the slate, ranks player
opportunities on merit (no per-league quota), explains **why** each stands out and
**what could go wrong**, and says so plainly when data is missing. See the
[Vision](docs/product/VISION.md).

## How the repo is organized

```
app.py            # thin shell: config, styles, migration, router, error boundary
router.py         # query-param navigation → Today or Game view (same tab)
domain/           # normalized models: SlateGame, Opportunity, Evidence, DataStatus
leagues/          # one adapter per league (MLB, WNBA, World Cup) + registry
services/         # data access (as_of), schedules, cache, snapshots, migrations, freshness
views/            # Today and Game screens
components/       # reusable UI/HTML (cards, feed, filters, date switch, …)
styles/app.css    # the single design-system stylesheet
src/              # ingestion + lower-level data (kept from the original build)
tests/            # offline pytest suite
docs/             # product / design / engineering / history knowledge base
data/ database/ logs/   # persistent local data (gitignored, not in the repo)
```

Where to add things (leagues, views, components, services, domain objects) is a
one-glance table in [Architecture](docs/engineering/ARCHITECTURE.md#where-things-live-quick-reference).

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m streamlit run app.py
```

The app needs `database/sportshub.db`, which is **not** in the repo (data is
gitignored). On a fresh clone, build it via the daily pipeline — drop a dated MLB
feed in `~/Downloads` and run `update.command` (or `python morning_update.py`).
Exact steps and the macOS double-click workflow: [Setup](docs/engineering/SETUP.md).

- Tests (offline): `pip install -r requirements-dev.txt && python -m pytest`
- Data diagnostics: `python diagnostics.py`

## Add a new league

1. Create `leagues/<name>/adapter.py` implementing the `LeagueAdapter` protocol
   (`fetch_schedule`, `match_team`, `opportunities`, plus display hooks).
2. `register(<Adapter>())` and import it in `leagues/__init__.py`.

That's it — no shared screens change. Details and the protocol:
[Architecture](docs/engineering/ARCHITECTURE.md).

## How to think about the product

Every screen has **one hero**, leads with the story over the statistic, and shows
evidence honestly (negative evidence is as prominent as positive). We **refine
before we redesign**. Read the [Experience Principles](docs/product/EXPERIENCE_PRINCIPLES.md)
before designing a screen, and the [Roadmap](docs/product/ROADMAP.md) (organized
around the user's day) before planning a feature.

## For AI assistants

Start with **[CLAUDE.md](CLAUDE.md)**, then the docs it links. Respect the
[Decision Log](docs/engineering/DECISION_LOG.md) — don't reverse a decision
without reading why it was made.

## Navigation model (current)

- **Today / Tomorrow** switch (same-tab links); independent league filter pills
  (none selected = show every sport with games that day); a chronological game grid;
  and a ranked cross-sport **Top Opportunities** feed.
- Click a game card to open its view. **MLB and WNBA games open dedicated editorial
  matchup pages** (see [MLB Game Page](docs/engineering/MLB_GAME_PAGE.md) and
  [WNBA Game Page](docs/engineering/WNBA_GAME_PAGE.md)); World Cup is schedule-only
  for now.
- If a league's live schedule is briefly unavailable, the most recent **cached**
  slate is shown; a genuinely empty slate shows no fallback
  ([degraded mode](docs/engineering/DECISION_LOG.md)).
