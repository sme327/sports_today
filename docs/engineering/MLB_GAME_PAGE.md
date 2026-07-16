# MLB Game Page (Phase 1)

> **Purpose** — How the MLB game page is built: its sections, data sources, what is deliberately not shown yet, and where Phase 2 plugs in.
> **Audience** — Engineers and AI assistants extending the game page.
> **Update when** — Sections, formulas, thresholds, or supported data change.
> **Related** — [Architecture](ARCHITECTURE.md) · [Decision Log](DECISION_LOG.md) · [Testing](TESTING.md) · [Design System](../design/DESIGN_SYSTEM.md)

An editorial, evidence-backed MLB preview. Every claim is traceable to stored
plate-appearance data; nothing is fabricated. The page reuses the shared
architecture (router → view → service/builder → domain model → components).

## Flow

```
router → views/game.py (dispatch by league)
       → views/mlb_game.py (renders sections)
       → services/app_cache.cached_mlb_game_page  (cache: game_id | as_of | engine version)
       → services/mlb_game_page.build_mlb_game_page  (assembles the model)
       → services/mlb_analytics  (pure numeric engine)
       → domain/mlb_game_page.MLBGamePage  (immutable model)
       → components/mlb_game.py  (pure HTML)
```

One `as_of`-bounded plate-appearance load feeds the whole page. Calculations live
in services; components only format. The page model is cached on
`game_id | as_of | mlb-game-page-v1`.

## Sections (Phase 1, order refined in V1.1)

Reading flow: **summary → evidence → synthesis → matchups → players → expected
game**. Team Identity (evidence) is placed above the story (synthesis).

1. **Game hero** — doubles as a game summary in plain English: full city + team
   names, venue, time, a recent-form phrase per team ("Bats heating up"), and each
   probable starter with handedness + a descriptor ("Elite strikeout stuff",
   "Command specialist", "Pitches to contact") derived from the same K/control
   percentiles. "Probable starters not yet available" when missing.
2. **Team Identity** — six dimensions per team: Power, Contact, Plate Discipline,
   Speed, RISP (league-relative percentiles shown as qualitative tiers + the
   number), and Recent Form (composite last-10 vs. season baseline → Trending
   Up/Down). A conversational, form-aware identity sentence.
3. **What This Game Is About** — three deterministic, role-tagged insight cards
   (Biggest Advantage · Swing Factor · Momentum). No free generative text.
4. **Key Matchups** — 3–5 offense-vs-probable-starter interactions with editorial
   headline questions ("Can Nola command the strike zone?"); explanations keep the
   exact analytics. Team-vs-team fallback if a starter isn't matched.
5. **Heating Up / Cooling Off** — up to 3 each, gated by a minimum trend
   magnitude; fewer (or none) when the data doesn't support it. (Kept distinct from
   the team-level "Trending Up/Down" wording on purpose.)
6. **Players Positioned to Succeed** — the shared Opportunity engine (1+ Hit),
   filtered to the two teams, **same scores as the slate** (not rescaled), enriched
   with **team logo + player headshot** (also applied to homepage MLB opportunities).
7. **Expected Game Shape** — a multi-factor classification (Starter-driven,
   Power-oriented, Contact-heavy, Balanced, Uncertain), presented as a big label +
   a **plain-English narrative** + inline facets. Never "pitcher's duel".
8. **Storylines to Watch** — 2–3, only above a quality threshold; never padded;
   editorial article headlines marked with a small baseball icon (no numbering).

Small monochrome SVG icons (no emoji) mark identity dimensions, matchups,
storylines, and insight roles to aid scanning.
9. **Data context** — a compact line naming the `as_of` cutoff and what's excluded.

**Deliberately not added (V1.1):** a separate "Players To Watch" section (duplicates
the hero's starters + Heating/Cooling, and "biggest star" has no honest data
source) and a separate "Game At A Glance" (would restate Team Identity) — its
summary intent is folded into the enriched hero instead.

## Data sources

- **MLB StatsAPI schedule** (via the MLB adapter): teams, logos, venue, status,
  probable-pitcher names.
- **Stored plate appearances** (`plate_appearances`, `as_of`-bounded): all team,
  player, and pitcher metrics. Pitchers are matched to the probable-starter names.

## Formulas & thresholds (documented in `services/mlb_analytics.py`)

- Identity composites are weighted blends of league percentiles (`POWER_W`,
  `CONTACT_W`, `DISCIPLINE_W`, `SPEED_W`, `RISP_W`) — transparent heuristics, not
  models. Recent Form uses `FORM_W` (35% TB/PA, 25% reach, 15% hit, 15%
  K-avoidance, 10% BB), last-10 vs. season baseline.
- Samples: RISP ≥ 50 to show (≥ 100 full confidence); Speed ≥ 10 attempts;
  pitcher ≥ 100 PA faced; trends recent ≥ 15 PA / baseline ≥ 35 PA; trend
  magnitude ≥ 0.6 (composite z-score).

## Not shown in Phase 1 (no reliable data yet)

Confirmed/projected lineups, bullpen freshness/rankings, defensive rankings,
weather, park factors, injuries, catcher throwing, pitch arsenal/type matchups,
Statcast quality-of-contact, betting odds, win probability, and score prediction.
Win–loss records are intentionally not manufactured; Recent Form uses underlying
offensive indicators instead.

## Phase 2 extension points

- Add matched-pitcher context (season lines) once a reliable source exists.
- Add lineup/bullpen/park/weather as new services + matchup types (guarded by
  availability, following the same "omit or label honestly" rule).
- Grade the opportunity picks against results (see Roadmap → After Games).
- New opportunity markets plug into the existing scorer and the section reuses it.
