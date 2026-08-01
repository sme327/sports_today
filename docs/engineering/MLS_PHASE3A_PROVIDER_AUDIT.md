# MLS Provider Audit (ESPN)

> **Purpose** — What real MLS data ESPN provides, how reliable each field is, and what is absent — the reference behind the MLS team-data integration and the plan for what to collect next.
> **Audience** — Engineers extending MLS collection (events, players, lineups).
> **Update when** — The provider's coverage changes, or a new endpoint/field is adopted.
> **Related** — [MLS Game Page](MLS_GAME_PAGE.md) · [MLS Phase 1 Inspection](MLS_PHASE1_INSPECTION.md) · [Decision Log](DECISION_LOG.md)

_Findings from a read-only audit of ~18 completed 2026 MLS matches (24 clubs, varied
scorelines/draws/cards), verified against the live endpoints. No new provider was
introduced; everything is ESPN._

## Endpoints

Host `site.api.espn.com/apis/site/v2/sports/soccer/usa.1` unless noted.

| Endpoint | Returns | Used for |
|---|---|---|
| `…/scoreboard?dates=YYYYMMDD` | events (id, competitors, status, season slug) | schedule + event discovery |
| `…/summary?event={id}` | `boxscore`, `rosters`, `keyEvents`, `standings`, `gameInfo`, `header` | the one payload with everything analytical |
| `site.web.api.espn.com/apis/v2/sports/soccer/usa.1/standings?season=YYYY` | two conference groups w/ rank, points, W/D/L, GF/GA | standings (richer than summary-embedded) |

**Regular-season filter:** `event.season.slug == "regular-season"` (type `13846`).
Excludes Leagues Cup, U.S. Open Cup, Concacaf, friendlies, and playoffs.

## Team match stats — collected (100% coverage)

From `summary.boxscore.teams[].statistics` — **all 28 fields present in every sampled
match**. Values live in `displayValue` (the numeric `value` is null for soccer);
counts are integer strings, `*Pct` are lossily-rounded decimals.

- **Shooting:** totalShots, shotsOnTarget, blockedShots, (derived shot accuracy)
- **Possession/passing:** possessionPct (0–100, provider), totalPasses, accuratePasses,
  (derived pass %), totalCrosses, accurateCrosses, (derived cross %), long balls
- **Set pieces / discipline:** wonCorners, foulsCommitted, offsides, yellowCards,
  redCards, penaltyKickGoals, penaltyKickShots, saves
- **Defensive actions:** totalTackles, interceptions, totalClearance

> **Handling:** counts stored as ints; possession from the provider; shot/pass/cross
> accuracy **derived from raw counts** (more precise than the rounded `*Pct`); missing
> field → NULL (never 0). **Absent entirely:** aerial duels, expected goals (xG).

## Standings — collected (100%)

Dedicated endpoint gives both conferences (15 teams each): `rank`, `points`,
`gamesPlayed`, `wins`, `ties`, `losses`, `pointsFor` (GF), `pointsAgainst` (GA),
`pointDifferential` (GD). Stored as dated snapshots (`mls_standings`).

## Available but NOT yet collected

- **Match events** (`summary.keyEvents`, 100%): goal scorer + assist, goal minute, goal
  subtype (header/volley/penalty/free-kick), own goals, yellow/red + minute + player,
  substitutions (in + out + minute). *This is the recommended next increment (Option C):
  cheap (same payload), high narrative value.* Field/goal coordinates are also present
  (a future shot-map hook).
- **Rosters / formation** (`summary.rosters`, 100%): formation (e.g. 4-2-3-1), starters,
  subbed-in/out flags, jersey, position, `formationPlace`, athlete id/name/headshot.
  Enough for a **projected/confirmed lineup** and pitch fill — a later phase.

## Player stats — thin (deferred, Option B)

Player stats exist only in `summary.rosters[].roster[].stats` (not `boxscore.players`,
which is empty for MLS) and are a **limited attacking/discipline set**: goals, assists,
shots, shots on target, fouls (committed/suffered), offsides, cards, own goals; GK adds
saves/goals-conceded/shots-faced. **Absent at player level:** minutes, passes/passing
accuracy, chances created, tackles/interceptions/clearances, touches. Too thin for an
honest, differentiated Players-to-Watch → **deferred until a richer source exists.**

## Identifiers (all stable)

- **Event id** — numeric, per-competition. **Team id** — stable numeric, identical across
  matches/events (join on this, never on name). **Athlete id** — numeric + guid.
  **Venue id**, **season** (year + type `13846`, slug `regular-season`),
  **competition** slug `usa.1` / league id `770`.
- Display names carry accents/variants ("CF Montréal", "St. Louis CITY SC"), but team
  ids are always present → **join on `team_id`/`event_id`**; aliases are for display only.

## What this enables (recap)

| Data | Status | Powers |
|---|---|---|
| Team match stats | ✅ collected | Snapshot, Tactical proxies, Attacking, Discipline, Storylines |
| Standings | ✅ collected | Hero standing, table-gap storylines |
| Match events | ⏭️ next (Option C) | Timeline cues, goal-scorer storylines |
| Rosters/formation | later | Projected/confirmed lineups, pitch fill |
| Player stats | ⛔ deferred (Option B) | Players to Watch — blocked on richness |
| xG / tracking | absent | — (needs a different provider) |
