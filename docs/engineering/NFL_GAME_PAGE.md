# NFL Matchup Page

> **Purpose** — How NFL archive and current-slate matchup pages are built: pipeline, sections, formulas, data vintage, and leakage model.
> **Audience** — Engineers and AI assistants extending NFL (and a template for any league built on an ingested season feed).
> **Update when** — Sections, formulas, thresholds, the feed shape, or the archive/slate split change.
> **Related** — [Architecture](ARCHITECTURE.md) · [Sport Plans → NFL deep-dive](../product/SPORT_PLANS.md#nfl-deep-dive-matchup-page-the-flagship) · [Decision Log](DECISION_LOG.md) · [Testing](TESTING.md)

The flagship deep-dive. NFL analysis is built from **completed, ingested games**, while
the ESPN slate identifies tonight's actual matchup. An upcoming game therefore gets its
own pregame page from aggregated prior data; an archived game can additionally show what
actually happened, giving the page a built-in backtest.

## The archive/slate split (read this first)

**NFL appears on two surfaces, joined since 2026-08-11 by an id bridge:**

| Surface | Source | What you get |
| --- | --- | --- |
| Today's slate | ESPN scoreboard + ingested prior seasons | **Matchup →** opens tonight's own pregame page when both teams resolve. Week 1 uses the latest earlier season and labels that vintage; after games are played it uses only the current season before kickoff. |
| Season archive (`?view=nfl`) | Ingested Big Data Ball seasons in `sportshub.db` | Week browser → full matchup deep-dive for any ingested game. |

The two surfaces still use different identity spaces — ESPN event ids
(`401772980`) on the slate, vendor `game_id` (`46033-SFO@PHI`) in the feed.
**`services/nfl_bridge.py` reconciles them on date + teams**, not on ids, because no id is
shared. Both sides carry full team names, so it never decodes `SFO@PHI`; names normalise
through the feed's own `nfl_teams` dimension so a rebrand does not break the join. Week is
**not** a join key — ESPN calls a wild-card game "week 1 of the postseason" and the feed
calls it week 19. Dates match within one day, because ESPN start times are UTC and a
Sunday-night kickoff lands on Monday.

**A feed-game match is not required before kickoff.** The vendor feed contains played
games, so an upcoming ESPN event cannot have a vendor `game_id`. `can_preview()` instead
checks that both teams resolve, and `build_nfl_pregame_page()` builds tonight's page.
It never substitutes an old game: prior seasons supply aggregated team/player context
only. Unknown teams still fall through to the honest schedule-only page.

`supports_deep_dive` is now **True** for NFL, but that is a *league capability*; whether a
given game has a page is decided per game by `NFLAdapter.deep_dive_available()`, which
cards consult before offering a link. Offering a "Matchup →" that lands on "not connected"
is precisely the dishonesty the product rules forbid.

**The cadence is wired; the data is not there yet.** `services/nfl_feed_refresh.py` runs
inside the daily rebuild and imports a `*nfl-season-team-feed*.xlsx` +
`*nfl-season-player-feed*.xlsx` pair dropped in `~/Downloads` — idempotent by file
fingerprint, silent when there is none, non-fatal on failure, **Downloads only** (an
automated job must not search a personal documents tree). So mid-season, dropping a feed
is all it takes for today's NFL cards to start deep-diving.

The 2026 page sharpens as weekly feeds arrive. Week 1 explicitly says when it is using
2025; later weeks use 2026 games strictly before kickoff. NFL props remain pending until
the weekly vendor result feed arrives.

Entry point: the `/nfl/` route (`web.views.nfl_archive`),
rendered only when `nfl_team_games` actually holds data — so a fresh clone with no NFL
feed shows no dead link.

## Flow

```
web/urls.py (`/nfl/`) → web.views.nfl_archive
             → services/nfl_game_page.py    (season pills → week pills → game cards → matchup)
       → services/nfl_game_page.build_nfl_game_page(game_id)   (deterministic builder)
       → services/nfl_repository.py     (reads nfl_team_games / nfl_player_games)
       → services/nfl_analytics.py      (pure football engine)
       → src/nfl_opportunity.py         (reachable-bar player props)
       → components/nfl_game.py         (pure HTML)
```

Daily slate path: `web.views.game` → `web.nfl.pregame_context` →
`build_nfl_pregame_page` → the same analytics/components, with no final-score badges.

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

The page is built for three depths of reading (ten seconds, a minute, longer) and runs
game → thesis → personnel → strategy → numbers → players → props → supporting detail →
methodology. Three layout patterns keep it from reading as one stream of equal cards:
**editorial** (full width, prose at a reading width), **comparison** (away left, home
right, thin rules between rows inside one card) and **matchup** (offense → defense). See
the decision log, 2026-09-09.

1. **Hero** — team marks, teams, round label (`Week N` / `Wild Card / Playoffs · Wk N`),
   records *coming in*, final score, winner. No market line (odds display is scoped to
   NCAAF). The marks (and the small one on every team column) come from the collected
   `nfl_schedule` — ESPN's own logo URLs, never constructed — via `team_logos()`; a
   database without that table renders the page without them, and without placeholders.
2. **Tonight's matchup** *(note; editorial)* — the hand-written story of the game: a
   headline, up to four observations with a bold lead and an orange dot, and "the other
   way". Written before any line.
3. **Availability** *(note; comparison)* — Out → Doubtful → Questionable → PUP, name
   strongest, status badge, context muted; departures under their own rule.
4. **The read** (`_thesis`; editorial) — the engine's synthesized, factual thesis rendered
   as three labelled ideas: *X wins if* (each team's offense tiered by league percentile
   against the other's defense — the sentence is the engine's, "vs" read as "beats" under
   the label), and *Watch* for the clearest rush/pass mismatch (offense percentile minus
   inverted defense percentile ≥ 30) and a turnover-battle note (margin gap ≥ 0.6). Empty
   at season open. Tiers: elite ≥ 85, strong ≥ 65, middling ≥ 35, else weak.
5. **Matchup at a glance** *(matchup)* — **team identity**: seven rows (points, points
   allowed, yards/play, rush yards, pass yards, 3rd-down %, turnover margin) with league
   percentile chips; an even row is muted and the advantaged side is brighter. Then the
   **battlefields** as two cards, "When X has the ball", each with the pass and rush
   offense against the other's defense, the percentiles the edge came from, and the edge
   (percentile gap ≥ 20, else Even) — the section's one orange.
6. **Player spotlights** *(comparison)* — per team, each key player's leakage-safe prop as
   a badge beside the name, the evidence line, the measured matchup call, and on a played
   game a ✓/✗ against what they actually did.
7. **Prop board** *(note; comparison)* — every posted line evaluated, over / under /
   pass, calls ranked ahead of passes, "N calls out of M evaluated" in the subtitle. One
   row anatomy: name, direction (strongest badge), confidence (quieter), the market, the
   why in muted prose. (The 2026-09-09 note keeps its three older lists — Prop leans,
   Volume board, Looking for overs — because those calls were recorded before kickoff.)
8. **Recent form** *(support)* — last 5 results (oldest → newest) with the record and
   points for/against, one strip per team.
9. **Rest & schedule** *(support; in season only)* — `rest_days` per team from game
   dates; flags a short week (≤ 4 days), off a bye (≥ 13), or a rest edge (≥ 3 days).
10. **Since last season** *(note; support)* — who moved, the player emphasized and the
    detail a whisper.
11. **What would change the read** *(note; editorial)* — the falsifiers, then
    **Before seeing the lines** *(note; appendix)* — the directional reads from before any
    line, flat chips, never graded; a `<details>` closed by default.
12. **Methodology** — the disclaimer and the note's sources, separated and quiet.

The report container is wider than the rest of the site (1320px against 1160px, via
`.site-shell:has(> .nfl-report)` in `web/static/web.css`): comparisons, the glance grid and
the two-column prop lists take the width; every run of prose keeps a `ch`-based cap.

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
- **Registered and slate-scored** (2026-08-18). Five markets in `domain/markets.py`, all
  over-only; `score_nfl_opportunities` ranks the whole population, not just spotlights.

### What the bars are worth

Backtested leakage-safe on 10,552 scored player-games — each scored on that player's prior
games only, then checked against the game itself. **Base rate .542**; served props (70+)
hit **.650, +10.8 over base**. Per market: rushing attempts **+18.6**, receptions
**+10.6**, receiving yards **+8.8**, passing yards **+6.5**, rushing yards **+5.2**.

The threshold ladders are measured, recorded inline in `_STAT_MARKETS`: each rung is about
10 points rarer than the one below it. Four alternative score shapes were tested out of
sample and all lost to the incumbent. Details and the corrected earlier figures are in the
[Decision Log](DECISION_LOG.md) (2026-08-19).

## Matchup effect on a player

`services/nfl_matchup.py`. A defence is rated by how far players fell short of — or beat —
**their own** baselines against it, which removes the confound that a defence's schedule
decides who it faced. Rolling 34-game window: an all-time mean is dominated by rosters that
no longer exist, a season-only rating is silent until about week 10.

Defences are a real, persistent trait (split-half r .14–.52). What that trait is *worth to
a player* is where it gets interesting — easiest-fifth minus hardest-fifth, against the
game-to-game sd:

| stat | swing | game sd | rated? |
|---|---|---|---|
| passing yards | +43 | 96.9 | **yes** |
| rushing yards | +10 | 39.1 | **yes** |
| receiving yards | +2 | 35.3 | no |
| receptions | +0.3 | 2.5 | no |
| rush attempts | +0.6 | 6.7 | no |

**The matchup moves quarterbacks and running backs and does not move receivers or usage.**
Usage is a coaching decision; defences do not touch it.

### The effect is one-sided — there is no "excel" call

Mean gap against the player's own baseline, 95% intervals, across the full spectrum:

| defence | passing yards | rushing yards |
|---|---|---|
| very tough | **−15.1 ±10.5** | **−4.0 ±3.0** |
| tough | **−21.6 ±12.9** | −2.0 ±3.2 |
| average | −3.1 ±8.6 | −0.9 ±2.4 |
| soft | −4.3 ±14.6 | +1.7 ±4.0 |
| very soft | +4.5 ±15.5 | +1.8 ±3.9 |

A tough defence reliably suppresses; a soft one does nothing. Every soft-side interval
covers zero and the merely-soft passing band is *negative* — the likely reason is game
script, since a bad defence means a lead, and a lead means running the ball and resting
starters. **A test guards that no code path can predict an above-baseline day.**

The page therefore shows one of four states: `Tough matchup` (the only prediction, with
the yardage), `Soft on paper` (names the non-finding explicitly), `Matchup not a factor`
(receivers, with one footnote per page rather than one per player), or nothing at all for
an average defence. Only the negative chip carries colour.

### Two honesty rules specific to football

- **A window that predates the current season is disclosed, not excluded.** A mostly
  prior-season window clears 50.1% against 54.5% for a clean one. Dropping those games
  buys +1.0 point for 22% fewer props — a bad trade, so the risk line names them
  (`8 of these 10 games are from last season`) and *stability* takes the hit, not the
  opportunity score. The pick isn't wrong; our confidence that the sample still describes
  the player is what weakens.
- **A player is one player, not one player per team.** Identity comes from his most recent
  game, history from every game he has played. Grouping on team split traded players into
  fragments and cost 459 of them their track record at week 3 of 2025.

## Game notes (hand-authored, per game)

`services/nfl_game_notes.py` reads `content/nfl/<espn_event_id>.toml` — a dated, sourced
note a person wrote for **one game** — and the pregame page carries it as four sections:
**Availability** (the official injury report, with its date), **Since last season** (who
moved, in and out), **Tonight's shape** (a written read, stated as a read) and **Prop leans**
(ranked most to least confident, stated as not scored), with the sources at the foot.

Why it exists: on 2026-09-09 the week-1 page spotlighted a Seahawks running back who had
signed with Kansas City, a Patriots receiver who had been released, and a rookie ruled out
that morning — the 2025 feed cannot see an offseason. The honest fix for the day was a note
that says who is out or gone, so the engine stops spotlighting them, and carries what a
person had to say about the game.

Rules the code enforces:

- **A sidelined player is removed before the pick, not after.** `Out`, `PUP`, `IR`,
  `Departed` and `Suspended` drop the player from the picking frame, so `key_players`
  chooses the next man up (Stevenson replaced Henderson). `Questionable` is shown and
  does nothing else — dropping him would be a prediction about the report. Matching is on
  the feed's printed name, because a hand-written note has no id another source shares.
- **The note is part of the page's identity.** Its content fingerprint is folded into the
  matchup cache key (`web/nfl.py`), so editing the file re-renders without an engine bump.
- **A malformed note fails loudly** (an unknown status or lean direction raises), because
  a typo would otherwise silently keep spotlighting the player it meant to remove.
- **The disclaimer changes.** With a note, injuries are on the page — hand-entered, dated,
  and in none of the numbers — and the footer says exactly that instead of "not modeled".
- **No market lines.** Leans are the author's read written before a line was consulted.
  Odds are displayed nowhere on an NFL page (they sit beside props we score) and consumed
  nowhere (decision log 2026-09-02).

### Three kinds of call, kept apart

The note holds three lists that look alike and are not, and the page labels each:

| Section | Written | Has a number? | Graded? |
|---|---|---|---|
| **Before seeing the lines** | before any line was posted | no | **no** — an anti-bias record of the read before the market spoke |
| **Prop board** *(notes from 2026-09-10)* | every posted line, over / under / **pass** | yes: stat, line, side, confidence (none for a pass) | calls yes; a pass is recorded as evaluated, never graded, so the page can say "3 calls of 17 evaluated" |
| Prop leans / Volume board / Looking for overs *(the 2026-09-09 note only)* | against the posted lines | yes | yes |

The split exists because a directional read with no number ("Stevenson receptions, over")
is not a prediction anyone can score, and one of them reversed the moment a line appeared
(3.5 was above anything his usage supported). Grading only what was called against a real
number, after the number existed, is what makes the record honest. The overs are their own
block because the project's one measured matchup effect argues only for unders; an over
has to rest on usage, and the reader should see that it does.

Two more hand-written pieces sit inside the page's structure: `[read] game_script`, the
expected shape of the game, rendered as a fourth panel under The read and labelled as a
read; and `[[falsifiers]]`, **What would change the read**, an editorial card near the
foot listing the conditions that would falsify the page, written before kickoff so the
game can be watched against them. Availability entries with an `impact` line rank above
the rest, which collapse to name and status under "Also on the report". The glance grid
carries one generated sentence, **What it says** — who leads on more ranked rows and where
the widest percentile gap is — description only, computed in the component.

### The ledger (`/leans/`)

`services/nfl_leans.py` records every graded call into `nfl_lean_ledger` when the note is
recorded (idempotent; a re-record after an edit keeps the grade) and settles it from ESPN's
box score (`src/espn_nfl_boxscore.py`) once ESPN marks the game final. Vocabulary is the
prop ledger's: hit / miss / void, a player absent from the box score is a **void** (he did
not play, and a zero would grade an under as a hit), a whole-number push is a void. Both
halves run in the daily rebuild, non-fatally, and by hand as `python -m scripts.nfl_leans`.
The page shows the record overall and split by section, confidence, side and stat, then
every call by game with its actual — and prints no hit rate until something is decided.
**Volume plays** (attempts, completions, receptions, wherever the call was made) get their
own running tile, because the owner's hunch is that usage is where the edge lives, and the
rule in `content/nfl/README.md` is that every posted attempts and receptions line gets a
call every week so that record is complete rather than a selection. The natural next
surface is the per-player volume chart, planned in
[NFL Player Volume Charts](NFL_PLAYER_VOLUME_CHARTS.md).

This is a seam, not the destination: the obvious pipe is ESPN's injury report and current
roster collected in the daily run, which would fill Availability for every game and retire
the Departed list. Until then a note is written the day of the game.

## Not shown (honest gaps)

Injuries and roster changes only where a hand-authored note exists (above). No weather, travel, snap counts, personnel groupings, EPA/DVOA/success rate,
or drive-level context. No possession-adjusted efficiency — `yards_per_play` is the
stand-in and is labeled as such. No live or current-season data: the archive is only as
current as the last ingested feed.

## Extension points

- The analytics module is football-generic — NCAA Football could reuse it given a
  comparable feed.
- ~~Reaching the live slate needs an ESPN↔vendor ID bridge~~ — **done**
  (`services/nfl_bridge.py`, matched by date + teams).
- ~~Registering the props in `domain/markets.py`~~ — **done 2026-08-18**; grading and
  Performance coverage follow once a 2026 feed exists to grade against.
