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
web/              # Django renderer + static export: Today, matchups, Results, Performance
domain/           # normalized models: SlateGame, Opportunity, Evidence, DataStatus
leagues/          # one adapter per league (8: MLB, WNBA, MLS, World Cup, NFL, NHL, NBA, NCAAF) + registry
services/         # data access (as_of), schedules, cache, snapshots, migrations, freshness, analytics
components/       # reusable UI/HTML (cards, feed, filters, date switch, …)
styles/app.css    # the single design-system stylesheet
src/              # ingestion + scorers (kept from the original build)
scripts/          # CLI entry points (daily update, collectors, feed imports, diagnostics)
tests/            # offline pytest suite (web/tests/ covers the renderer and export)
docs/             # product / design / engineering / history knowledge base
data/ database/ logs/   # persistent local data (gitignored, not in the repo)
```

Where to add things (leagues, views, components, services, domain objects) is a
one-glance table in [Architecture](docs/engineering/ARCHITECTURE.md#where-things-live-quick-reference).

## Run the public site locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver
```

The app needs `database/sportshub.db`, which is **not** in the repo (data is
gitignored). On a fresh clone, build it via the daily pipeline — drop a dated MLB
feed in `~/Downloads` and run `python -m scripts.morning_update` (data only;
`update.command` does the same **and** publishes, so it needs wrangler set up).

For the zero-cost Cloudflare Pages deployment, `update_and_publish.command` runs the
same local update, exports the public site, and publishes the finished snapshot. The
Mac only needs to be online during that workflow; Cloudflare serves the site afterward.
Exact steps and the macOS double-click workflow: [Setup](docs/engineering/SETUP.md).

- Tests (offline): `pip install -r requirements-dev.txt && python -m pytest`
- Build and audit the static site: `python -m scripts.publish_pages --build-only`
- Force the local recurring strength scan: `python -m scripts.signal_discovery --force`
- Data diagnostics: `python -m scripts.diagnostics`

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
- Click a game card to open its view. **MLB, WNBA, and MLS games open dedicated
  editorial matchup pages** (see [MLB Game Page](docs/engineering/MLB_GAME_PAGE.md),
  [WNBA Game Page](docs/engineering/WNBA_GAME_PAGE.md), and
  [MLS Game Page](docs/engineering/MLS_GAME_PAGE.md)). **An NFL slate game whose
  season is in the ingested feed opens the NFL deep-dive matchup page** —
  `services/nfl_bridge.py` joins the live slate to the feed by date + teams; preseason
  and un-ingested seasons get the schedule-only page instead (see
  [NFL Game Page](docs/engineering/NFL_GAME_PAGE.md)). NFL also scores five over-only
  player-prop markets onto the slate when its feed is fresh (silent when it is six-plus
  weeks stale, which is every preseason day). World Cup, NHL, NBA, and NCAA Football
  are schedule-only.
- **Schedule-only doesn't mean uncurated.** Those games carry a team-level read —
  records, ranks, conference and postseason stakes — as a chip on the card and a
  "The read" section on the game page (`services/editorial.py`). Cards also show
  competition context (a football week, a neutral site, "Elimination game", or where
  a baseball game sits in its series) whenever it says something the reader doesn't
  already assume.
- The NFL **archive browser** (`/nfl/`) remains a local development/review tool and is
  deliberately excluded from the public static site; the NFL **matchup pages** for
  bridged slate games do publish (the export follows the card's redirect).
- If a league's live schedule is briefly unavailable, the most recent **cached**
  slate is shown; a genuinely empty slate shows no fallback
  ([degraded mode](docs/engineering/DECISION_LOG.md)).

## Prediction evaluation

- Every published prediction scoring **70+** is a **qualifying prediction** and is
  graded, including predictions reached through a matchup page.
- The highest-ranked eight are additionally marked **Featured** because they appear
  on Today. Performance can compare All qualifying, Featured, and Other qualifying.
- Lower-scored rows may remain in the private ledger for score research, but are not
  included in public performance results.
- Performance reports prediction counts alongside independent slate counts. Scores
  are ranking signals, not probabilities.

See [Prediction Evaluation](docs/engineering/PREDICTION_EVALUATION.md) for the full
evaluation contract and model-development guardrails.
