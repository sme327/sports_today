# Picks Shortlist

> **Purpose** — The plan for prop "selection": the owner marks the props they
> like, gets an easy list when placing a bet, and sees their own record the next day.
> **Status** — **Shipped 2026-08-20** as planned. The affordance is a bookmark button on
> every `.op-row` (one component serves the Today feed and all game pages, so one tray
> covers both — the open question resolved itself); the tray, storage and Results join
> live in `web/static/static-site.js`; rows carry `data-pick-*` / `data-player-id`
> attributes so the script parses no rendered text. Hard boundaries held: no odds, no
> stakes, no backend.
> **Update when** — Scope changes (e.g. a cross-device v2 is considered).
> **Related** — [Roadmap](ROADMAP.md) · [Vision](VISION.md) · [Decision Log](../engineering/DECISION_LOG.md)

## What it is

A device-local shortlist. On a game page or the Today feed, each prop row gets a
selection affordance; tapping it saves the pick. A floating tray ("3 picks") lists the
day's selections with one primary action: **copy / share as text** (`navigator.share`,
so iOS opens the share sheet — text it to yourself, or paste into a sportsbook search).
The next day, the Results page joins the stored picks against the graded rows it already
renders and shows **"Your picks: 3/4"** — a personal record with no server and no login.

## Why it fits

The product answers "what should I pay attention to today?" — this is the natural last
step of that moment: capture the answer. It uses only what already exists (every prop is
snapshotted and graded), and the static site can do all of it client-side.

## Hard boundaries (product rules, agreed)

- It is a **shortlist, not a bet slip**: no stakes, no odds, no payout math. This keeps
  the no-odds rule intact (enforced by test for editorial; keep the spirit here).
- **Device-local v1.** `localStorage`, keyed by slate date. No accounts, no sync. A
  cross-device version would need a small Cloudflare KV function — explicitly out of
  scope for v1.
- Selection uses **orange** — `styles/app.css` already reserves orange for
  "the score + selection"; this is the selection that comment anticipated.

## Implementation sketch

- **Storage**: `localStorage` entries per slate date:
  `{date, league, player_id, player_name, market_key, market, threshold, score}`.
  Auto-expire dates older than ~14 days on load.
- **Affordance**: a tap target on prop rows in `components/opportunity_feed.py` and the
  game-page prop lists; rows carry `data-*` attributes so the script needs no parsing.
- **Tray**: small component + logic in `web/static/static-site.js` (already shipped for
  live scores). Count chip → panel → share/copy/clear.
- **Results join**: graded rows in `components/results_feed.py` already render
  player/market/result; stamp them with `data-player-id`/`data-market-key` and join
  client-side against the stored picks for the "Your picks: N/M" line.
- **Export note**: zero impact on the static export — all state is client-side; no new
  crawled pages.

## Open questions for the implementer

- Where the affordance lives on the compressed mobile row without crowding it
  (Experience Principles screen checklist applies).
- Whether the Today feed's curated eight and a game page's full list share one tray
  (they should — one list per slate date).

## Explicitly parked (same conversation)

- **Results-page client-side filters / row compression / verdict header** — proposed
  2026-08-20, owner didn't love it as framed; parked, revisit only with a fresh look.
- **Scheduled morning run (launchd)** — owner is thinking about it; do not build.
