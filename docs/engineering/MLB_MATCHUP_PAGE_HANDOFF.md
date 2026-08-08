# MLB Matchup Page — Handoff & Current State

> **Purpose** — A pick-up-and-go briefing for any agent (or human) about to refine or expand the MLB matchup page: what it shows today, *why* it's built this way, where the code lives, and the honest seams to grow from.
> **Audience** — Anyone working on the MLB game page next.
> **Update when** — The MLB page's sections, data, or product rules change.
> **Related** — [MLB Game Page (engineering reference)](MLB_GAME_PAGE.md) · [Architecture](ARCHITECTURE.md) · [Experience Principles](../product/EXPERIENCE_PRINCIPLES.md) · [Decision Log](DECISION_LOG.md) · [Testing](TESTING.md)

## TL;DR
The MLB matchup page is an **editorial, evidence-backed preview** that answers one
question: *"which individual matchups matter most today, and why?"* Baseball is a
game of repeated one-on-one interactions (hitter vs. pitcher, offense vs. starter),
so the page is built around **team offensive identity, hitter/pitcher matchups, who's
hot/cold, and the strongest 1+ hit opportunities** — every claim traceable to stored
plate-appearance data. It is deliberately **not** a stat dump, a win-probability
model, or a betting sheet.

Open it by clicking any MLB game card on the Today page. Nothing on it is fabricated:
if the data can't support a claim, the section shrinks or says so.

## The product intent (the "why" behind everything)
These rules are load-bearing — respect them when refining:

- **Explainable, always.** Every number carries human-readable evidence. The evidence
  *is* the product, not decoration.
- **Honest about data.** Missing/thin data → the section omits, shrinks, or labels
  itself; it never invents. No manufactured win/loss records, no fake "biggest star."
- **Heuristics, not black-box models.** Identity scores are transparent weighted
  blends of **league-relative percentiles** — anyone can read the weights. We say
  **percentile/tier**, never "probability," until a calibrated model exists.
- **Leakage-safe by construction.** Everything is computed from plate appearances
  **strictly before** the slate date (`as_of`). Historical windows never see the
  future.
- **Refine before redesign.** Improve hierarchy, wording, and craft before adding
  structure. A change that adds vertical space or cognitive load without adding
  understanding is a regression.

## What's on the page today (sections, in render order)
Reading flow is **summary → evidence → synthesis → matchups → players → expected game**.

1. **Hero (doubles as a plain-English summary).** City + team names, venue, time; a
   recent-form phrase per team ("Bats heating up"); each probable starter with
   handedness + a descriptor ("Elite strikeout stuff", "Command specialist", "Pitches
   to contact") derived from K/control percentiles. Falls back to "Probable starters
   not yet available." *Why: orient the reader in ~5 seconds without a separate glance
   section.*
2. **Team Identity.** Six dimensions per team — Power, Contact, Plate Discipline,
   Speed, RISP, and Recent Form — shown as qualitative **tiers + the number**
   (league-relative percentiles), plus a conversational identity sentence and
   strengths/vulnerabilities. *Why: evidence before story; this is the analytical
   backbone.*
3. **What This Game Is About.** Three deterministic, role-tagged insight cards —
   **Biggest Advantage · Swing Factor · Momentum**. No free generative text. *Why: a
   synthesis a fan can repeat, built only from the computed identity/edges.*
4. **Key Matchups.** 3–5 offense-vs-probable-starter interactions with editorial
   headline questions ("Can Nola command the strike zone?"); the explanation keeps the
   exact analytics. Team-vs-team fallback when a starter isn't matched. *Why: the
   signature of a baseball page — the one-on-one battles.*
5. **Pitcher Trends.** Both probable starters: per-start **strikeout** and
   **hits-allowed** sparklines (inline SVG) with a direction arrow and season K%,
   plus the SP props we're serving with their clear-rate. *Why: a starter's recent
   trajectory is what earns (or withholds) confidence in his props.* Built by
   `services/mlb_trends.py`.
6. **Player Trends (enriched).** Replaces plain Heating/Cooling: per-game **1+-hit
   dot rows**, **L5 / L10 / L25** windows, current **hit streak**, and support/risk
   evidence. Leads with **≥ 90-conviction** picks, then heating/cooling movers;
   falls back to the plain Heating/Cooling section when the enriched build is empty.
   *Why: the score alone doesn't build conviction — the trajectory behind it does.*
7. **Players Positioned to Succeed.** The shared **1+ Hit opportunity engine**,
   filtered to the two teams, **same scores as the slate** (not rescaled), with team
   logo + player headshot, and **today's confirmed-lineup awareness** (slot evidence,
   bench-cap, honest not-posted state). *Why: reuse the one tested scorer; consistency
   with the homepage feed.*
8. **Expected Game Shape.** A multi-factor label (Starter-driven / Power-oriented /
   Contact-heavy / Balanced / Uncertain) + a plain-English narrative + inline facets.
   Never "pitcher's duel." *Why: sets expectations for the *kind* of game, without
   predicting a score.*
9. **Storylines to Watch.** 2–3, only above a quality threshold, never padded;
   editorial headlines with a small baseball icon. *Why: the "why this game is
   interesting," earned from data.*
10. **Data context.** A compact line naming the `as_of` cutoff and what's excluded.

Small monochrome SVG icons (no emoji) mark identity dimensions, matchups, storylines,
and insight roles to aid scanning.

**Deliberately *not* on the page (and why):** a separate "Players To Watch" (duplicates
the hero's starters + Heating/Cooling, and "biggest star" has no honest source) and a
"Game At A Glance" (would restate Team Identity — its intent is folded into the hero).

## How the numbers are made (transparent heuristics)
All weights/thresholds are module constants in `services/mlb_analytics.py`:

- **Identity composites** = weighted blends of league percentiles:
  Power `{tb/pa, hr/pa, xbh_rate}` (equal), Contact `{hit .5, k_avoid .3, reach .2}`,
  Discipline `{bb .45, pitches/pa .35, reach .20}`, Speed `{attempts .5, sb_success .5}`,
  RISP `{risp_hit, risp_reach, risp_tb/pa}` (equal).
- **Recent Form** `FORM_W` = 35% TB/PA · 25% reach · 15% hit · 15% K-avoidance · 10% BB,
  last-10 vs. season baseline (`FORM_TREND_POINTS = 5.0` index-point move to call it up/down).
- **Sample gates:** RISP ≥ 50 to show (≥ 100 full confidence); Speed ≥ 10 attempts;
  pitcher ≥ 100 PA faced to profile; trends need recent ≥ 15 PA / baseline ≥ 35 PA and
  a composite z-score magnitude ≥ 0.6 (`TREND_MAGNITUDE`).

## Data sources & constraints
- **MLB StatsAPI schedule** (via the MLB adapter): teams, logos, venue, status,
  probable-pitcher names.
- **MLB StatsAPI lineups** (`hydrate=lineups`, via `src/mlb_lineups.py`): today's
  posted batting order, joined to batters by MLB player id (= the feed's
  `batter_id`). Used to add confirmed-slot evidence and cap scratched batters.
- **Stored plate appearances** (`plate_appearances`, `as_of`-bounded): all team,
  player, and pitcher metrics. Pitchers are matched to probable-starter names.
- **Grain:** plate-appearance level, current season only. **No** Statcast (exit
  velocity, pitch type), no bullpen/park/weather/injuries; **confirmed lineups are
  now used** (when posted), but matched-starter season lines and the rest remain the
  honest limitations and the main gate on expansion (see below).

## Where the code lives
```
router → views/game.py (dispatch: league == "MLB")
       → views/mlb_game.py            # renders sections (order above)
       → services/app_cache.cached_mlb_game_page   # cache: game_id | as_of | engine
       → services/mlb_game_page.py    # build_mlb_game_page — assembles the model
       → services/mlb_analytics.py    # pure numeric engine (weights/thresholds here)
       → services/mlb_trends.py       # pitcher per-start + batter per-game trend spotlights
       → src/opportunity.py           # the 1+ hit scorer (shared with the homepage; lineups= overlay)
       → src/mlb_lineups.py           # today's posted lineups (StatsAPI); Lineups model
       → src/pitcher_opportunity.py   # SP strikeouts / hits-allowed scorer (two-directional)
       → domain/mlb_game_page.py      # immutable MLBGamePage model (section shapes + trend models)
       → components/mlb_game.py       # pure HTML (mlb-* CSS in styles/app.css)
```
Cached on `game_id | as_of | mlb-game-page-v1`. Calculations live in services;
components only format. Tests: `tests/test_mlb_game_page.py`.

## How to see it
```bash
cd "/Users/sme/Documents/Projects/sports today" && source .venv/bin/activate && python -m streamlit run app.py
```
Pick a slate date in the sidebar that your loaded MLB data covers, then click an MLB
game card. For *current* games, refresh the feed first (`./update.command`).

## Where to refine or expand (the honest menu)
Refinements that need **no new data** (safest, "refine before redesign"):
- Tighten wording/hierarchy in any section; reduce vertical space without losing meaning.
- Revisit the identity **weights/thresholds** (they're heuristics — tune with evidence).
- Sharpen **Key Matchups** selection/headlines, or the **Game Shape** narrative.
- Improve the **descriptor language** (pitcher/form phrases) for precision + honesty.

Already shipped from this menu (kept here as reference for how they were done):
- **Confirmed lineups** → slot evidence + bench-cap + honest not-posted state
  (`src/mlb_lineups.py`; see the 2026-08-04 Decision Log entry).
- **SP pitcher props** (strikeouts, hits allowed; two-directional) in the feed.
- **Grade the opportunity picks** against results → the Results view + grading loop.

Expansions that still need **new data** (each must follow "omit or label honestly"):
- **Projected lineups** before official posting; **expected plate appearances** from
  slot + pace.
- **Matched-pitcher season lines** once a reliable source exists.
- **Bullpen freshness, park factors, weather** → new services + matchup types.
- **New opportunity markets** (total bases, batter strikeouts, walks **already
  shipped** — `src/tb_opportunity.py`, `src/batter_kbb_opportunity.py`): a `MarketSpec`
  entry in `domain/markets.py` + a scorer —
  grading, classification, and display then work automatically (see the 2026-08-05 and
  08-06 [Decision Log](DECISION_LOG.md) entries).

**Do not** add win probability, score prediction, or Statcast-flavored claims until the
data genuinely supports them — that's the line that keeps the page trustworthy.

---
*This handoff reflects the MLB page as shipped (V1.1/V1.2 refinements). The deeper
per-formula reference is [MLB_GAME_PAGE.md](MLB_GAME_PAGE.md); the section rationale and
what was deliberately omitted are logged in the [Decision Log](DECISION_LOG.md).*
