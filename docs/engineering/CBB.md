# College Basketball — what we know, and the plan

> **Purpose** — What the ingested CBB data contains, why CBB is the most promising unbuilt
> sport in this app, why it should stay **team-level**, and the phased plan.
> **Audience** — Engineers and product.
> **Status** — **Nothing in the app reads CBB.** No adapter, no schedule, no view. Two
> seasons of vendor data sit in SQLite, used by nothing.
> **Related** — [Historical Data](HISTORICAL_DATA.md) · [Method](METHOD.md) · [Decision Log](DECISION_LOG.md) · [Sport Plans](../product/SPORT_PLANS.md)

---

## 1. Why CBB at all

One number. `corr(closing line, |final margin|)` — how well *anything* predicts whether a
game will be competitive:

| sport | from the line | from records |
|---|---|---|
| **CBB** | **+0.531** | — |
| NBA | +0.195 | +0.098 |
| MLB | +0.047 | +0.031 |

**Basketball at the college level is the one sport in this app where competitiveness is
genuinely predictable.** MLB games are close-or-not almost at random — even the market
only manages +0.047 — which is why MLB editorial could never be calibrated against
outcomes and why `richer_game_outcomes` was killed.

The product's central question is *"what should I pay attention to today?"*. CBB is the
sport where that question has a real answer, and it is also the sport with the most games
to sift — which is exactly the curation problem this app exists to solve.

| closing spread | n | mean margin | within 5 pts |
|---|---|---|---|
| pick'em (<3) | 2,351 | 8.94 | **37.3%** |
| 7-12 | 2,475 | 11.54 | 28.9% |
| 20+ | 902 | 27.50 | **3.3%** |

---

## 2. What we hold

`cbb_team_games` and `cbb_player_games`, loaded by `scripts/import_boxscore_feed.py`:

| season | games | teams | conferences |
|---|---|---|---|
| 2024-25 | 6,294 | 705 | 31 |
| 2025-26 | 6,293 | 726 | 31 |

**Team rows carry the richest context of any feed we have**: `conference`, `division`
(`NCAA D1` or null for non-D1 opponents), `arena`, `venue` (Home/Road/**Neutral** — CBB is
the only feed with neutral sites), `pace`, `poss`, `oeff`, `deff`, halves (`1h`, `2h`,
`ot_total`), plus **odds at ~91% coverage** (opening/closing spread, total, moneyline).

Player rows: 10,943 players, 254,919 player-games, with minutes, shooting splits, rebounds,
assists, steals, blocks, turnovers.

**Gaps:** two seasons only, no data before 2024-25, and neutral-site games are excluded
from any home/road analysis rather than mishandled.

**Volume, measured:** 43.7 games per day on average across a 144-day season, peaking at
**169** (2025-11-03), 155, 149. This is the constraint that shapes everything below.

---

## 3. Why this should stay team-level

The instinct not to go player-level is right, and the data says so plainly.

**Player turnover is 63% a year.** Of the 8,503 players in 2024-25, only **3,149 (37%)**
appear in 2025-26. Graduation, transfers and the portal churn the population annually.
Compare MLB, where the same batters recur for a decade. So:

- There is almost no multi-season player history to build a prior from — and
  [Method §2](METHOD.md) shows that prior-season priors did not even help in **MLB**,
  where the history is far deeper.
- Median games per player-season is **19**, and only 52% of player-games reach 20 minutes.
  Roles are volatile — foul trouble, blowout minutes, a rotation that changes weekly.
- Any per-player estimate would be shrunk almost entirely to the mean, which is exactly the
  conclusion `batter-hit-v5` reached in a sport with much more data.

**And the demand side is thin.** Prop markets barely exist for most of 6,300 games; a
Tuesday in January is 100+ games across 31 conferences of mostly-anonymous rosters. The
app would be scoring props nobody can bet, for players nobody is watching — the exact
failure that retired total bases.

**Recommendation: no CBB player props. Team-level editorial only.** Revisit only if a
future season shows a stable, followable subset (a top-25 subset with real prop markets),
and only against the [Method](METHOD.md) gates.

---

## 4. The real design problem: volume

This is the thing to solve before writing any code.

MLB's slate is ~15 games. **CBB's is 100+ on a weeknight.** The product rules say *rank the
whole slate on merit* and *no forced quota by league* — applied naively to CBB, one sport
would swamp every other league on the page, and a "best game" chosen from 100 unknowns is
not curation, it is a lottery.

CBB therefore needs a **curation gate of its own** before it earns slate space. Options, in
rough order of appeal:

1. **Exclusion first** *(now the measured recommendation)* — drop games records flag as
   likely blowouts (gap ≥ .40 cuts the within-5 rate by 11.9pp and covers ~12% of the
   slate), then apply an interest floor to what remains. Detecting a bad game is about
   three times more reliable than detecting a good one, so filter before you rank.
2. **Ranked / conference-relevant only** — top-25 involvement, conference games, rivalry.
   Simple and defensible, but the ranking source is a new dependency.
3. **Collapse to a CBB section** — one "college basketball" block with its own top-N rather
   than 100 cards in the shared grid.

**Non-D1 opponents must be excluded or clearly marked.** `division` is null for them; a
D1 team beating a non-D1 side by 40 is not a signal, and those games would otherwise
dominate any "mismatch" reading.

---

## 5. The plan

Deliberately phased so each step is useful alone, and so we can stop after any of them.

### Phase 0 — Schedule only *(small, but there is a trap)*

A `leagues/cbb/adapter.py` subclassing `ScheduleOnlyESPN` with
`espn_path = "basketball/mens-college-basketball"`, registered like NHL/NBA/NCAAF.

**⚠️ It must set `espn_groups = (50,)` and `espn_limit = 300`, or it is silently broken.**
ESPN's college-basketball scoreboard defaults to a small subset, and truncates to `limit`
after filtering. Verified against our own vendor feed on four dates:

| date | our feed | ESPN default | `groups=50`, limit 100 | **`groups=50`, limit 300** |
|---|---|---|---|---|
| 2026-02-11 | 54 | **5** | 54 | **54** |
| 2026-01-10 | 149 | **19** | 100 | **149** |
| 2025-11-03 | 169 | **19** | 100 | **169** |

The default would have shown **19 of 169 games** and said nothing. Both settings are
already supported by `ScheduleOnlyESPN` (added 2026-08-11); the adapter just has to declare
them. Do **not** raise the limit further — ESPN handles very large values badly
(`limit=900` returned 19 where `limit=100` returned 45 on NCAAF).

**Ship gate:** the slate does not become unusable. At 169 games on a peak night it will,
so Phase 1's curation gate almost certainly has to land first — see §4.

### Phase 1 — Editorial + a curation gate *(the real value)*

Team-level signals from ESPN records — this is where CBB earns its place, and it is the
only sport where those signals can be *validated against something*. Adds conference
context (the feed's `conference` field is a genuine editorial angle no other league has:
races, rivalry, tournament implications).

**Ship gate:** measured against outcomes, per [Method §1 and §6](METHOD.md). A CBB signal
must beat its base rate, and must add something the closing line does not already contain —
the test that killed the NBA fatigue signal.

### Phase 2 — Matchup page via a feed bridge *(medium)*

Exactly the NFL pattern, already built and proven: `services/cbb_bridge.py` joining a live
ESPN game to its vendor row on **date + teams**, a per-game `deep_dive_available()` so
cards never offer a dead link, and honest copy when a season is not loaded. Team identity
(pace, efficiency, halves), form, conference standing.

**Blocked on the same thing NFL is:** a current-season feed. Our data ends 2026-04-02, so
live games will not bridge until an in-season CBB feed is dropped in `~/Downloads` — the
pickup mechanism already exists (`services/nfl_feed_refresh.py` generalises).

### Phase 3 — March Madness *(seasonal, already on the roadmap)*

Bracket, seeds, regions, upset watch. The tracker already carries `march_madness_*`. CBB
Phases 0-2 are its prerequisite, and neutral-site handling matters here specifically.

### Explicitly **not** planned

Player props, player spotlights, any per-player scoring — see §3.

---

## 6. Open questions

- ~~**Does a CBB editorial signal beat its base rate?**~~ **Tested 2026-08-11 — yes.**
  `corr(record gap, |margin|)` is **+0.2367** against MLB's +0.031, and mismatches
  (gap ≥ .40) drop the within-5 rate by **−11.9pp**. Two caveats that shape Phase 1:
  **quality is inverted** (both-good games are *less* close, −2.4pp, the opposite of MLB's
  `even`), so use the **gap only**; and records add just **+0.066** once the line is
  controlled for, with **nothing** in close-line games. Lead the gate with **exclusion** —
  dropping likely blowouts is ~3x more reliable than picking good games. Full numbers in
  the decision log.
- **Where does the conference tendency go?** Over/under rates correlate r = +0.252 between
  seasons across 29 conferences — above the umpire null (+0.057) but only ~1.3 SE from zero
  at n=29. More seasons would settle it. Not a betting angle; possibly an editorial one
  ("this conference plays fast").
- **Women's basketball** is a separate feed we do not hold, and a separate product
  decision. The tracker's `march_madness_womens` assumes it.
