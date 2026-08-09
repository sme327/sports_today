# Sport Plans — the per-sport view

> **Purpose** — A by-sport cut of the expansion plan: where each sport stands and its
> tiered path forward. Complements the [Roadmap](ROADMAP.md) (strategy) and the
> project tracker (the *sequenced, dated* plan + capability matrix). This is the "what
> does the full arc for **this** sport look like?" view.
> **Audience** — Product + engineering (and future-me picking one piece to build).
> **Update when** — A sport advances a tier or its plan changes.

## How to read this

Every sport climbs the same **tiers** (each an independent chip-away unit):

- **T0 · Schedule-only** — the games appear on the slate. One adapter; hours.
- **T1 · Live state** — period/quarter/inning, clock, possession (when the source is reliable).
- **T2 · Player props** — a stats pipeline (game logs / play-by-play) + a scorer built on
  the **reachable-bar reliability discipline** (`src/reliability.py`), then snapshot + grade.
- **T3 · Matchup deep-dive** — an evidence-first, calm page that explains the game.
- **T4 · Postseason / tournament** — a **Top Today** spotlight with series/bracket context.

Status: ✅ shipped · 🟡 partial · ⬜ planned · 🚫 out of scope.

Sports are grouped by **family** because a foundation is built once and reused.

---

## Baseball — MLB

The most mature sport; the template for everything else.

- **T0/T1** ✅ Schedule, live state, final scores.
- **T2** ✅ Batter props: 1+ hit, total bases, strikeouts (2+/3+), walks (1+/2+); SP
  strikeouts + hits allowed (over/under). All on the reachable-bar discipline, graded daily.
- **T3** ✅ Matchup deep-dive (SP trends, batter spotlights, team analysis).
- **T4** ⬜ Postseason mode: series model, rotation/short-rest flags, bullpen workload,
  postseason-vs-regular samples kept distinct.
- **Next levers:** better inputs (opposing-SP quality, park, weather, bullpen — currently
  *not* modeled and stated as such); batter-hit top-end de-saturation; proven-edge tier.

## Basketball — WNBA → NBA → NCAA → March Madness

One **basketball foundation** (extracted from WNBA) serves every league below.

**WNBA** — ✅ schedule/live, ✅ props (points/rebounds/assists, reliability-floored),
✅ matchup page, ✅ grading (fixed). Next: playoffs mode; more markets (3PM, stocks,
double-doubles) if they clear the reliability bar; score top-end polish.

**NBA** — 🟡 T0 schedule-only shipped (pre-staged). Path: extract the basketball
foundation → T2 props (P/R/A + threes, stocks) → T3 matchup page (reuse WNBA's) →
T4 Playoffs/Finals (series + bracket).

**NCAA Basketball (M/W)** — ⬜ T0 schedule-only → editorial matchup (team stories first;
**no player props for now** — data breadth). Feeds March Madness.

**March Madness (M/W)** — ⬜ T4 the marquee tournament spotlight: configurable bracket
(don't hardcode 68), seeds/regions, upset watch, tournament-specific matchup pages over
the shared basketball analytics, daily briefing. Both tournaments, equal depth.

## Football — NFL → NCAA FB → UFL

**NFL is the flagship deep-dive** (its own section below). NCAA FB is editorial-only;
UFL is data-gated.

**NFL** — 🟡 T0 schedule-only shipped. Then: T1 ingest the vendor feed → T2 props →
**T3 the deep matchup page** → T4 playoffs/Super Bowl. See **[NFL deep-dive spec](#nfl-deep-dive-matchup-page-the-flagship)**.

**NCAA Football** — 🟡 T0 schedule-only shipped (rank prefix `#5 Georgia`, week label).
🚫 **No player props** (roster breadth / data). Its value is games, team edges, upset
watch, rivalry/conference context, and **CFP** implications → T4 College Football Playoff
mode (bracket, campus/neutral sites, selection-state honesty).

**UFL** (spring, formerly XFL/USFL) — ⬜ T0 schedule-only + editorial; props only if a
reliable stat source exists (treat as data-availability-gated). T4 championship spotlight.

## Hockey — NHL

Standalone, but the **best-fitting new prop sport**: its core stats are per-game counts
that drop straight into the reachable-bar model.

- **T0** 🟡 Schedule-only shipped. **T1** ⬜ period+clock live-state.
- **T2** ⬜ Props from ESPN box scores: **shots on goal**, **points** (G+A) — over-only,
  reachable-bar; then **goalie saves**; blocks/hits if reliable. Collector mirrors
  `src/wnba_collector.py`.
- **T3** ⬜ Matchup page: shot-share/pace identity, projected goalie, form, injuries.
- **T4** ⬜ Stanley Cup Playoffs spotlight (series model).

## Soccer — MLS + World Cup → more leagues

- **MLS** — ✅ schedule/live, ✅ **full matchup page** (collected team-stat analysis).
  🚫 Player props **deferred** (no soccer player-stats pipeline yet).
- **World Cup** — ✅ schedule-only; ⬜ Top Today spotlight during the tournament.
- **Expansion** (EPL, Champions League, Liga MX, …) — ⬜ T0 schedule-only via the shared
  ESPN client is ~an hour each; player props stay deferred until a soccer stats pipeline
  exists. The MLS soccer client/collector/analytics is the reusable template.

## Future consideration (fits, but later)

- **Tennis** — a match *is* head-to-head, so it fits the matchup model surprisingly well:
  match preview (surface, form, H2H history, ranking), props (match winner as a pick, sets,
  games, aces), and Grand Slams as **Top Today** tournament spotlights (draw/bracket reuse).
  Real challenges: the draw/bracket structure, tour breadth (ATP/WTA), and a reliable stat
  source. A legit future **family**, not a one-off. Medium priority.
- **Golf** — **lowest priority** and a genuine model departure: no head-to-head matchup — a
  *field* of 100+ over four rounds, so it's a leaderboard/field model (props: make-cut,
  top-10, finish position, round scores), not a slate of matchups. Revisit only if the core
  is mature and there's appetite for a distinct "field event" surface.

## Deliberately out of scope

**Motorsport (F1/NASCAR)** and **combat (UFC/boxing)** — don't fit the model; out.
**Fantasy/DFS optimization** and **bracket-pool management** are also out. International
events (Olympics, WBC) are Top Today spotlight candidates (schedule + editorial), like the
World Cup.

---

# NFL deep-dive matchup page (the flagship)

> **Goal:** the deepest, most robust, most *useful* page in the product — while staying
> calm and honest. Not a dashboard dump; a page that answers **"what is this game about,
> where is the edge, and what should I actually watch?"** Every claim cites a real number;
> unmodeled/missing context (weather TBD, inactives not final) is shown as such; negative
> evidence is at least as prominent as supporting evidence; early-season small samples are
> labeled. Reuses the existing deep-dive component pattern (hero → snapshot → battlefields
> → spotlights → trends) proven on MLB/WNBA/MLS.

**Why it can be deep:** the Big Data Ball NFL feed on hand is granular — **63 team columns
and 75 player columns per game, full season** — enough for real offensive/defensive
identity, situational splits, and per-player volume/efficiency, joined to ESPN
schedule/context (rest, travel, weather, injuries).

## Sections

1. **Game thesis + projected script** — one-line "what this game is about," plus the likely
   *shape*: pace (plays/game), pass/run tilt, competitiveness vs blowout risk, and the
   **stakes** (playoff/division leverage, clinching/elimination). The thesis first; detail
   beneath.

2. **Team identity — offense & defense, both sides, with league-percentile context.**
   - *Offense:* pace & neutral pass rate, points/drive, EPA/play + success rate, explosive
     -play rate, red-zone TD%, 3rd-down%, giveaway rate, pressure/sack rate allowed.
   - *Defense:* yards & EPA/play allowed, **pass vs run splits**, pressure/sack rate,
     red-zone defense, points/drive allowed, takeaway rate.
   - Rendered as a side-by-side comparison so strengths/mismatches read at a glance.

3. **Positional battlefields — where the game is won.** The decisive matchups, each citing
   real numbers with an honest "who has the edge" read (and the counter): pass offense vs
   pass defense; run offense vs run defense; O-line vs pass rush (pressure/sack rates);
   WR–CB shadow matchups when identifiable.

4. **Player spotlights + prop outlook — the payoff.** Key players tied to the matchup:
   recent form (game-log trend, L5/L10), the matchup angle (e.g. a soft run defense → RB
   volume/yards edge), and the connected **prop** with evidence + main risk. This is where
   the deep team analysis *connects* to the props rather than sitting beside them.

5. **Context that moves NFL games (honesty-gated — shown only when reliable, else labeled).**
   - **Rest & schedule spot:** days rest, bye, short week (Thu), off a primetime game.
   - **Travel:** distance, time zones crossed, altitude, body-clock (West team, early kick).
   - **Weather:** wind (passing/kicking), precip, temperature, dome vs outdoor.
   - **Injuries/participation:** key outs/questionable and the snap-share implications.

6. **Situational & scheme profiles.** Script-dependent tendencies (leading vs trailing),
   2-minute, 4th-down aggressiveness, pass-rate-over-expected (a coaching fingerprint).

7. **Recent form & trends.** Last-N form per team, home/away splits, units trending up/down
   — real numbers, small-sample language early in the year.

8. **Stakes & standings.** Playoff/division leverage, seeding, clinching/elimination (the
   competition-context + bracket models), so a Week 14 division game *reads* like one.

## Historical season browser (build + validate against a full past season)

A completed season is the *ideal* thing to build NFL against — every matchup, playoff
game, and the Super Bowl already exists, so we don't wait for live games to accrue (the
pain the current markets hit). The plan is to make the whole season **browsable**:

- **Ingest a full completed season** → team-game + player-game tables.
- **A season/week browser** (extends the existing slate date-nav): jump to any week or
  game in the archive.
- **Two views per past game:** the **leakage-safe pre-game deep-dive** (analysis as it
  would have appeared, using only data before kickoff) *and* the **final result / box
  score** (what actually happened, and how any prop edges would have graded).
- **Bonus: an instant season-long backtest** — see how the props/edges graded across an
  entire season at once, not one live slate at a time.

**Data note (honest):** the feed on hand (pulled 2026-01-12) has the full 2025 **regular
season + Wild Card round** (weeks 1–19), but not the divisional/conference/Super Bowl games
— those were played after that pull. A fresh re-download of the now-completed 2025 season
feed includes the entire playoffs + Super Bowl. So "browse last season incl. playoffs/SB"
is fully possible; it just needs the completed-season file, not the mid-January snapshot.

## Build order (tiers within NFL)

- **T1 · Ingest** ⬜ vendor feed → team-game + player-game tables (mirrors `src/ingest.py`;
  handle the two-row category+field headers). **Data is on hand.**
- **T2 · Props** ⬜ volume first (rush att, targets/receptions, pass att) → yards
  (rush/rec/pass) → TDs → defensive (tackles) — each a `MarketSpec` + a scorer, snapshot +
  grade. Distribution-based, not just reachable-bar (yards are continuous — likely a line
  around a projection with an honest hit-rate, same "never a longshot" discipline).
- **T3 · Matchup page** ⬜ V1 (identity + battlefields + form + context) → V2 (connect props
  as spotlights + situational/scheme profiles).
- **T4 · Postseason** ⬜ playoff-race context → playoffs mode → one highly-curated Super Bowl
  page, then a football calibration review by market/band/sample before widening coverage.

## Non-negotiables (inherit the product rules)

- **Explainable always** — every metric is inspectable; no opaque "power ratings."
- **Negative evidence ≥ supporting** — the page must say what could go wrong.
- **Honest about data** — missing/stale/unmodeled context shown as such; never invented.
- **No forced depth** — if a game is a mismatch with little to say, say that; don't pad.
- **Calm, one scannable screen** — thesis first, layered detail; refine before adding.
