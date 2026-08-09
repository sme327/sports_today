# NFL Matchup Page

> **Purpose** — How the NFL deep-dive is built: its pipeline, sections, formulas, the leakage model, and why it lives in the season archive rather than the daily slate.
> **Audience** — Engineers and AI assistants extending NFL (and a template for any league built on an ingested season feed).
> **Update when** — Sections, formulas, thresholds, the feed shape, or the archive/slate split change.
> **Related** — [Architecture](ARCHITECTURE.md) · [Sport Plans → NFL deep-dive](../product/SPORT_PLANS.md#nfl-deep-dive-matchup-page-the-flagship) · [Decision Log](DECISION_LOG.md) · [Testing](TESTING.md)

The flagship deep-dive. Unlike MLB/WNBA/MLS — which preview *tonight's* games from
live schedules — NFL is built against **completed, ingested seasons**. That makes it
the only page in the app that can show both a genuine leakage-safe preview *and* what
actually happened, which is what gives it a built-in backtest.

## The archive/slate split (read this first)

**NFL appears twice in the app, and the two are not connected:**

| Surface | Source | What you get |
| --- | --- | --- |
| Today's slate | ESPN scoreboard, via `ScheduleOnlyESPN` | Schedule-only card. `supports_deep_dive` is **False**, so `views/game.py` renders the honest placeholder. |
| Season archive (`?view=nfl`) | Ingested Big Data Ball seasons in `sportshub.db` | Week browser → full matchup deep-dive for any ingested game. |

`views/game.py` deliberately does **not** dispatch NFL. The two surfaces use different
identity spaces — ESPN event IDs on the slate, vendor `game_id` (`AWAY@HOME` form) in
the feed — and nothing reconciles them. Connecting them is real work (an ID bridge
plus a current-season feed cadence), not a missing `if` branch. Until that exists, a
live NFL game genuinely has no deep-dive, and the placeholder is the honest answer.

Entry point: a **sidebar** link on the Today view (`views/today._nfl_archive_link`),
rendered only when `nfl_team_games` actually holds data — so a fresh clone with no NFL
feed shows no dead link.

## Flow

```
router (view == "nfl") → app.py dispatch
       → views/nfl_archive.py           (season pills → week pills → game cards → matchup)
       → services/nfl_game_page.build_nfl_game_page(game_id)   (deterministic builder)
       → services/nfl_repository.py     (reads nfl_team_games / nfl_player_games)
       → services/nfl_analytics.py      (pure football engine)
       → src/nfl_opportunity.py         (reachable-bar player props)
       → components/nfl_game.py         (pure HTML)
```

Engine version: `nfl-matchup-v1` (`services/nfl_game_page.ENGINE_VERSION`).

## Ingest

`src/nfl_ingest.py`, run via `python -m scripts.import_nfl_feed`. Two workbooks per
season — a **team** feed (one row per team per game) and a **player** feed (one row per
player per game) — plus a shared `TEAMS` dimension sheet.

- **Multi-row headers flattened.** The team feed has 2 header rows (category / field),
  the player feed 3 (super-category / sub-category / field), and field names repeat
  across categories (`YDS`/`TD`/`ATT` under Passing, Rushing, Receiving). `_column_names`
  forward-fills the category rows and prefixes the field, yielding unique readable
  names (`passing_yds`, `rushing_att`, `receiving_rec`). Banner categories
  (`game_info`, `game_player_information`) are dropped from the prefix.
- **Season derived from the date**, not the file: NFL season *Y* runs Aug *Y* – Feb
  *Y+1*, so month ≥ 6 → that year, Jan–May → the prior year.
- **`season_type`** = `regular` for weeks ≤ 18, else `postseason`.
- **`opponent`** is derived by pairing the two team rows sharing a `game_id`.
- **Writes are additive per season** (`_replace_seasons`): loading 2023 replaces only
  2023 and keeps the rest. Falls back to a full replace on the first migration, when
  the table predates the `season` column.

Tables: `nfl_team_games`, `nfl_player_games`, `nfl_teams`, plus indexes on
`game_id`, `(team, game_date)`, and `(player_id, game_date)`.

## Leakage model

The strictest in the app, because the outcome is sitting in the same table.

- The preview is built from `prior` — games in **this game's season** with
  `game_date` strictly **before** the game's own date. Records, identity percentiles,
  battlefields, form, rest, and every player prop come only from `prior`.
- The final score is read separately from the game's own rows and shown as the
  **result**, never fed into the preview.
- Season scoping matters as much as the date bound: without it a Week 1 preview would
  inherit the previous season's profile. `game_id` is globally unique, so lookups
  never need the season.
- Player spotlights use `prior` for the pick and the **selected game's** row only to
  report what happened — the backtest.

## Sections

1. **Hero** — teams, round label (`Week N` / `Wild Card / Playoffs · Wk N`), records
   *coming in*, final score, winner.
2. **The read** (`_thesis`) — a synthesized, factual matchup thesis: each team's
   offense tiered by league percentile against the other's defense, plus a `Watch:`
   line for the clearest rush/pass mismatch (offense percentile minus inverted defense
   percentile ≥ 30) and a turnover-battle note (margin gap ≥ 0.6). Empty at season open.
   Tiers: elite ≥ 85, strong ≥ 65, middling ≥ 35, else weak.
3. **Rest & schedule** — `rest_days` per team from game dates; flags a short week
   (≤ 4 days), off a bye (≥ 13), or a rest edge (≥ 3 days' difference).
4. **Team identity** — seven rows (points, points allowed, yards/play, rush yards,
   pass yards, 3rd-down %, turnover margin) with league percentile chips and a
   better-side call.
5. **Battlefields** — each team's pass and rush offense against the other's
   corresponding defense. Edge when the percentile gap ≥ 20, else Even.
6. **Recent form** — last 5 results (oldest → newest) with points for/against.
7. **Player spotlights** — per team, each key player's leakage-safe prop plus a ✓/✗
   against what they actually did. No result shown when the player did not appear.

Honest notes: "Season opener — no prior-form data yet" at 0 prior games, "Early-season
sample — form is thin" below 4.

## Analytics

`services/nfl_analytics.py` — pure, deterministic, football-generic.

- **Defense is derived by pairing**, not from a defensive feed: a team's points/yards
  *allowed* are the opponent's offensive output in the same `game_id`. `team_game_frame`
  does the self-join and adds a `win` flag.
- `team_season_table` builds per-team offense + defense per-game profiles and league
  percentiles. "Bad" metrics are negated before ranking so a higher percentile always
  means better.
- Percentiles need ≥ 2 teams; with fewer, the table returns without percentile columns
  and the page falls back to raw-value comparisons.

## Player props

`src/nfl_opportunity.py`, on the same **reachable-bar** discipline as the other sports
(`src/reliability.highest_reachable_over`): offer a player the *highest* bar they clear
in ≥ 55% of their recent games — never an impressive bar they rarely reach.

- Last 10 games, minimum 4.
- Position → primary stat: QB → pass yards, RB/FB → rush yards, WR/TE → rec yards.
- `key_players` picks each team's QB (≥ 15 pass att/g), lead RB (≥ 8 rush att/g), and
  top 2 WR/TE (≥ 4 targets/g) by recent role.

**Not registered in `domain/markets.py`.** NFL props exist only as page spotlights;
they are not scored into the daily slate, snapshotted, or graded. Registering them is
the natural next step if NFL ever reaches the live slate.

## Not shown (honest gaps)

No injuries, weather, travel, snap counts, personnel groupings, EPA/DVOA/success rate,
or drive-level context. No possession-adjusted efficiency — `yards_per_play` is the
stand-in and is labeled as such. No live or current-season data: the archive is only as
current as the last ingested feed.

## Extension points

- The analytics module is football-generic — NCAA Football could reuse it given a
  comparable feed.
- Reaching the live slate needs an ESPN↔vendor ID bridge and a weekly feed cadence,
  then flipping `supports_deep_dive` and adding an NFL branch to `views/game.py`.
- Registering the props in `domain/markets.py` would give NFL grading and Performance
  coverage for free.
