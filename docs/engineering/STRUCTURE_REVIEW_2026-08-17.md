# Structure Review — 2026-08-17

> **Purpose** — A full pass over code and file structure after the Django migration and
> the Streamlit retirement: what is current, what is dead, what is duplicated, and what
> should change.
> **Audience** — You, and whoever picks this up next.
> **Scope** — Structure and code health. UI/UX is reviewed separately in
> [UX_REVIEW_2026-08-17.md](UX_REVIEW_2026-08-17.md).

---

## Verdict

**The structure is in good shape and the layering paid for itself.** Retiring Streamlit
removed ~2,000 lines and touched no scorer, no editorial rule, and no ingest path. That is
the direct return on the dependency-direction rule enforced back when `src/` and
`services/` were separated — the entire UI was replaceable because nothing below it knew
the UI existed.

Everything below is either already fixed today, or a specific recommendation. Nothing here
is structural alarm.

---

## 1. What was removed today

| removed | why |
|---|---|
| `app.py`, `router.py`, `run.command` | Streamlit entry points |
| `views/` (10 modules) | every surface has a Django route |
| `services/auth.py`, `services/app_cache.py` | Streamlit password gate and cache decorator |
| `components/empty_states.py`, `components/league_filters.py` | no importers |
| `components/results_feed.market_table_html` | imported Streamlit query params; uncalled |
| `functions/api/scores.js` | dead **and** non-functional — see §4 |
| `streamlit` dependency | uninstalled; suite and site build verified without it |

**Three pieces of logic were rescued rather than deleted with their callers**, because
their tests asserted invariants that still hold:

- the **curation-floor** test now checks `web/today.py` reads `grading.CURATION_FLOOR`
  rather than redeclaring one — that test exists *because* the number was duplicated once
  before, and the migration recreated exactly that risk;
- `_game_counts` re-points at `web.today`, which holds a byte-for-byte copy;
- `apply_filters` re-points at `web.analytics` — a **separate implementation**, not a
  rename (full key names vs query-param abbreviations), so the assertions were restated.

---

## 2. Layer sizes

| layer | files | lines | role |
|---|---|---|---|
| `domain/` | 6 | 1,214 | models, market registry — pure leaf |
| `src/` | 25 | 4,854 | ingest, collectors, scorers — headless |
| `services/` | 32 | 6,759 | reads, grading, editorial, page builders |
| `leagues/` | 20 | 1,027 | adapters + registry |
| `components/` | 14 | 2,102 | HTML fragments, framework-free |
| `web/` | 21 | 1,954 | Django views, templates, static export |
| `scripts/` | 13 | 1,094 | CLI entry points |
| `tests/` + `web/tests/` | 51 | 6,519 | 574 passing, 0 skipped |

**Test-to-code ratio is roughly 1:2.7**, which is healthy for a project whose whole premise
is "prove it before you build it".

`services/` at 6,759 lines is the one layer worth watching. It holds four distinct jobs
(data access, grading, editorial, page building). Not a problem yet; if it grows another
2,000 lines, split page builders into their own layer.

---

## 3. Duplication between `web/` and the shared layers

The migration copied two functions rather than importing them:

| function | copies | status |
|---|---|---|
| `_game_counts` | `web/today.py` (identical to the retired view) | **now single** — the old copy is gone |
| `apply_filters` | `components/filter_bar.py` and `web/analytics.py` | **now single** — filter_bar removed |

Both are resolved as of today, but the pattern is worth naming: **a migration that copies
instead of importing leaves two definitions of one rule, and they drift silently.** The
curation-floor test exists precisely to catch that class of bug, and it caught this one.

**Recommendation.** When the CBB or NHL surfaces land, import shared logic from
`services/` rather than copying it into `web/`. The `components/` layer is already
framework-free and consumed by Django — that is the pattern to follow.

---

## 4. The `/api/scores` Worker — dead *and* broken

Worth recording because the failure was invisible.

`functions/api/scores.js` was superseded by commit `262c3f8`, which moved live scores to a
browser-side fetch. Nothing had referenced it since. **It also could not have worked:**
ESPN blocks Cloudflare's egress IPs — measured today, the identical request returns **200
from this Mac and 403 from the Worker**. Both the Worker and the page's fallback swallowed
that into an empty array, so `/api/scores` answered `200` with `games: []` — indistinguishable
from "no games today" on a day with 11 MLB games.

Two wrong turns from the diagnosis, both worth remembering:

1. **Adding a polite `User-Agent` made it strictly worse.** ESPN 403s requests that
   *declare* a non-browser UA while allowing requests that declare none. The intuitive fix
   was the wrong one.
2. **A local test appeared to confirm the wrong hypothesis** — it was really this IP being
   rate-limited by my own probing.

The browser path is unaffected: ESPN serves `200` with `access-control-allow-origin: *` to
a request from the reader's own device.

---

## 5. Root-level files

```
manage.py                 Django entry point
requirements.txt          runtime deps (streamlit removed)
requirements-dev.txt      test/lint deps
setup.command             one-time install
update.command            data only
update_only.command       data only  ← identical in effect to update.command
update_and_publish.command  data + publish  ← the one you actually want daily
update_wnba.command       WNBA collector only
```

**Recommendation: remove `update_only.command`.** It differed from `update.command` only
by `--no-launch`, and that flag is now a no-op — Streamlit was the only thing it stopped
launching. Two files that do the same thing is how the wrong one gets run.

`update.command` should either become an alias for the publish flow or be renamed to make
the distinction obvious (`update_data_only.command`). Right now the *shortest, most
obvious* name is the one that leaves your phone showing yesterday's slate.

---

## 6. ~~Documentation drift~~ — **cleared 2026-08-18**

**14 files still describe Streamlit as the product.** Six of those are in
`docs/history/`, which is correctly archival and should be left alone. The live docs need
a pass:

| file | issue |
|---|---|
| `README.md` | describes launching the Streamlit app |
| `docs/README.md` | index still frames the product as Streamlit |
| `docs/engineering/ARCHITECTURE.md` | `views/` layer no longer exists; `web/` absent from the layer table |
| `docs/engineering/SETUP.md` | daily workflow ends at `update.command`, not publishing |
| `docs/engineering/TESTING.md` | claims 535 tests; actual is **574** |
| `docs/design/DESIGN_SYSTEM.md` | references Streamlit component constraints |
| `docs/product/ROADMAP.md` | deployment section predates Cloudflare Pages |
| `docs/engineering/MLB_MATCHUP_PAGE_HANDOFF.md` | Streamlit-era navigation |

`docs/engineering/DJANGO_MIGRATION.md` exists and is current — it is the right place to
point the others at.

**Done 2026-08-18.** Every live doc now describes the Django/static product. The pass
found more than the word "Streamlit":

- `TESTING.md` documented **two suites that no longer exist** (`test_auth.py`,
  `test_nfl_archive_app.py`) and omitted **thirteen that do** — including the whole
  `web/tests/` layer. Now 54 documented against 54 real, verified programmatically.
- `README.md` listed `app.py / views/` in the repo layout — deleted files.
- `SETUP.md` carried a full **"Deploying to Streamlit Community Cloud"** section, and
  pointed at three commands that no longer exist (`run.command`, `update_only.command`).
  Replaced with the Cloudflare Pages reality, including the three consequences worth
  knowing: updates come from the Mac, the URL is public, and cached pages need
  recomputing after a card change.
- Five per-league page docs described the Streamlit dispatch chain
  (`router → views/game.py`). They now name the Django path.
- Two docs referenced `src/tb_opportunity.py`, deleted when total bases was retired.

Three mentions were **kept deliberately**: the Decision Log and `docs/history/` are
archival, and `DESIGN_SYSTEM.md`'s "this should not feel like a dashboard someone
generated" is a design goal that outlived the framework it named.

**Guard added.** The audit is now mechanical: test count, documented-vs-real suites, and
referenced module paths are all checked by script rather than by reading.

---

## 7. Security note — the site is public

The Streamlit app had a password gate (`services/auth.py`). **A static export cannot have
one**, so the published URL is effectively public to anyone who has it.

That is probably fine — there is nothing personal in it, and the data is all public sports
information. But it is a real change from the previous setup and should be a decision
rather than a side effect. If you want it private, Cloudflare Access can gate the whole
Pages project without touching the app.

---

## 8. Recommendations, ranked

1. **Documentation pass** — 8 live files, most importantly the test count and
   `ARCHITECTURE.md`'s layer table. *Half a day.*
2. **Delete `update_only.command`**, and make the daily command unambiguous. *Ten minutes,
   and it prevents publishing the wrong thing.*
3. **Decide on public vs gated** for the published URL. *A decision, not work.*
4. **Import rather than copy** when the next surface lands. *A habit, not a task.*
5. **Watch `services/`** — split page builders out if it passes ~9,000 lines.

Nothing here is urgent. The structure is sound, the tests are honest, and the migration
was clean.
