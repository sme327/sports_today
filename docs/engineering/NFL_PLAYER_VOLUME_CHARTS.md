# NFL player volume charts — plan

> **Purpose** — The plan for a page that shows one player's game-by-game volume as a chart: a matchup, then a position, then one small chart per player. Written 2026-09-09 to be built after Week 1 has been played.
> **Audience** — Whoever builds it (next week), and the owner who asked for it.
> **Status** — **Planned, not built.** Nothing here exists in code yet.
> **Related** — [NFL Game Page](NFL_GAME_PAGE.md) · [Method](METHOD.md) · [Decision Log](DECISION_LOG.md) (2026-09-09)

## What the owner asked for

> "Another page where I can pull up a matchup and then a player (for example, QBs) and I get
> the yards per game and attempts per game for each QB in an easy to read graph (one per
> player). QB passing yards and attempts; WR/RB/TE receptions and targets."

The reason it matters is the lean ledger: the calls being graded every week are **volume
calls** (attempts, completions, receptions), and volume is a coaching decision the matchup
does not touch. A chart of a player's own games is the evidence a volume call rests on, and
the page should make the posted line easy to judge by eye without printing it.

## The page

- **Route** `/nfl/players/?game=<espn_event_id>&pos=QB` (also `WR`, `RB`, `TE`, and `REC`
  for every pass-catcher on both teams). Menu entry under NFL; exported for every game on
  the current slate with the two known controls, exactly as the schedule browser is (a
  bounded, enumerated set — never crawled).
- **Header** — the matchup (away at home, kickoff), the position pills, and a vintage line:
  *"2026 games, then 2025 shaded"* until the current season has enough games to stand alone.
- **Body** — one **small-multiple card per player**, both teams, the away team first. Each
  card: player, team, position, games shown, and **one chart** with two series on separate
  scales:
  - QB: **pass attempts** as bars (left axis), **passing yards** as a line (right axis).
  - WR/RB/TE: **targets** as bars, **receptions** as a line — the same y-axis, since both
    are counts and the gap between them *is* the catch rate.
  - Below the chart, the plain numbers: average, median, and last-5 for each series, plus
    the player's 2025 average with the vintage named. No forecast, no line, no score.
- **What it is not** — no market line drawn on the chart (odds are displayed nowhere on an
  NFL page and consumed nowhere; the reader brings the number), no projection, no colour
  that says "good". Description only, like every league surface.

## Data

| Season | Source | Grain | Targets? |
|---|---|---|---|
| 2023–2025 | ingested Big Data Ball player feed (`nfl_player_games`) | player-game | yes (`receiving_tar`) |
| 2026, in season | the same feed, dropped weekly into Downloads (`services/nfl_feed_refresh.py`) | player-game | yes |
| 2026, the days between a game and the next feed | ESPN box score (`src/espn_nfl_boxscore.py`, extend `_MAP` with `TGTS`) | player-game | yes |

Rule: **the feed is the record; ESPN fills the gap until the feed arrives**, and a game
present in both is read from the feed. Player identity across the two is the printed name,
the join the lean ledger already accepts (a `players` dimension keyed by ESPN athlete id is
the proper fix and is the same work the availability pipe needs — do them together).

Which players: `key_players` (`src/nfl_opportunity.py`) picks QB, lead RB and top-2
receivers by recent role. The charts page should be **broader**: every player on either
team with ≥ 3 games of the stat in the window, because the volume board calls lines on
fourth receivers and passing-down backs, and those are exactly the players `key_players`
excludes.

## The chart itself

Inline SVG, rendered by a pure function in `components/` (no library; the site is static
and the CDN allowlist is deliberately short). Read the `dataviz` skill before writing the
first line of it. Fixed points:

- x = game, oldest → newest, ticked by week; prior-season games in a lighter ink and
  separated by a rule with the season label, so the vintage is visible at a glance.
- Bars and a line in the two ink weights the design system already uses; **orange nowhere**
  unless it marks "this game" once the game is played (then the actual is a single marked
  point, matching the spotlight's ✓/✗ convention).
- One reference the reader can bring: the chart carries a light horizontal **median** line
  with its value labelled — the number a posted line is judged against.
- Mobile: cards one per row; the chart is ≥ 280px wide and scrolls inside its own container
  if the season gets long.

## Build order (one afternoon, after Week 1's feed or box score is in)

1. `services/nfl_player_volume.py` — `series(player, stat, before, seasons=2)` from the feed
   with the ESPN gap-fill; pure, tested on the synthetic DB the NFL page tests use.
2. `components/nfl_volume_chart.py` — the SVG; tested for shape (n bars, the median line,
   the vintage rule) not pixels.
3. `web/nfl_players_view.py` + template + route + menu link + export seeds (the slate's
   NFL games × positions) + the link-audit test the schedule browser has.
4. A "Charts →" link from each NFL matchup page's spotlights and volume board.
5. Docs: a section in `NFL_GAME_PAGE.md`, a decision-log entry, this file marked **built**.

## Open questions for the owner

- Targets are in the feed and in ESPN's box score (`TGTS`), so **receptions and targets** is
  cheap. **Routes run / snap share** is not in either source; the page will not have it.
- Should the page default to the current slate's game (today's) or remember the last one?
  Default to today, remembered per viewer in `localStorage`, is the suggestion.
