# WNBA Matchup Page

> **Purpose** — How the WNBA matchup page is built: its sections, data, formulas, and what is deliberately not shown yet.
> **Audience** — Engineers and AI assistants extending the WNBA page (and a template for a future NBA page).
> **Update when** — Sections, formulas, thresholds, or supported data change.
> **Related** — [Architecture](ARCHITECTURE.md) · [MLB Game Page](MLB_GAME_PAGE.md) · [Decision Log](DECISION_LOG.md) · [Testing](TESTING.md)

A basketball-designed matchup preview (not translated from baseball). Every claim
is traceable to collected box-score data; nothing is fabricated. It reuses the
shared architecture (router → view → cached builder → analytics → immutable model
→ pure-HTML components) and the design system.

## Flow

```
router → views/game.py (dispatch: league == "WNBA")
       → views/wnba_game.py (renders sections)
       → services/app_cache.cached_wnba_game_page  (cache: game_id | as_of | engine version)
       → services/wnba_game_page.build_wnba_game_page  (deterministic builder)
       → services/wnba_analytics  (pure basketball engine, as_of-bounded)
       → domain/wnba_game_page.WNBAGamePage  (immutable model)
       → components/wnba_game.py  (pure HTML; reuses mlb-* primitives + icons + opportunity feed)
```

One `as_of`-bounded player-game-log load feeds the whole page. `WNBAAdapter.
supports_deep_dive = True`; cached on `game_id | as_of | wnba-game-page-v1`.

## Sections (spec order)

1. **Hero** — team logos, names, records, tip time/venue, a featured player per
   team (top by impact), and the season series.
2. **Game Script** — a 2-sentence deterministic read classifying the style
   (fast-paced / defensive / contrasting / paint-oriented / perimeter) with the
   pivotal battle.
3. **Game Snapshot** — per-team cards: Last-5 record, streak, L5 scoring, L5
   defense, home/road record, rest days, season series.
4. **Team Identity** — labels (Elite offense, Defensive-minded, Three-point
   shooting, Transition, Paint-first, Ball movement, Rebounding, Rim protection)
   from league percentiles, plus a summary and W/L form dots.
5. **Where the Game Will Be Won** — 3–5 "battlefields" (Tempo, Perimeter, Paint,
   Turnovers, Rebounding) each with an explanation, supporting metrics, an
   advantage, and a confidence.
6. **Players Who Shape Tonight** — top players per team, role-classified
   (Superstar / Primary scorer / creator / Defensive anchor / Floor spacer /
   Rebounding presence) with season line, trend, strengths, and why they matter.
7. **Trending Players** — recent (last-5) vs. season baseline, categorized
   (Trending Up / Potential Breakout / Expanded Role / Recent Slump / Trending
   Down); gated by a minimum magnitude; no player in both up and down.
8. **Team Trends** — inline-SVG sparklines per team (points, opp points, 3PT%,
   rebounds) over the last 8 games.
9. **Strongest Player Opportunities** — the shared WNBA opportunity engine
   (points/rebounds/assists), filtered to the two teams, same scores as the slate.

## Data & engine

- **Source:** `wnba_player_game_logs` (ESPN box scores via `src/wnba_collector.py`).
- **`services/wnba_analytics.py`** (pure, basketball-generic, reusable for NBA):
  `team_game_frame` (per-team box score + the opponent's, paired by `game_id`),
  `team_season_table` (season profile + league percentiles), `recent_form`,
  `rest_days`, `season_series`, `player_season_frame`, `player_trend_frame`.
- **Composites are transparent heuristics.** Tempo uses a **combined-scoring pace**
  (observed total points in a team's games), not a possession/pace estimate. Trends
  use a composite z-score (points/minutes/rebounds/assists deltas), min 0.6, with a
  minimum recent-minutes filter.

## Not shown in this version (honest gaps)

Injuries/availability, confirmed or projected starters, rest/travel effects,
defensive assignments, and advanced ratings (pace, offensive/defensive/net rating,
possession estimates) — none are collected or claimed. Missing data yields empty
states, not guesses. See the spec's Future Data Roadmap.

## Extension points

- The analytics module is basketball-generic — a future **NBA page** can reuse it
  by feeding NBA logs (only the collector + adapter differ).
- Advanced ratings, injuries, and projected lineups plug in as new collected data
  + new battlefields/snapshot cards, following the same "omit or label honestly" rule.
