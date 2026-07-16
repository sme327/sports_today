# Sports Today — Future Endeavors

**Purpose**  
Define the next major product tracks for Sports Today, clarify how they connect, and prevent short-term features from becoming accidental substitutes for the larger experiences we ultimately want.

**Audience**  
Product owner, engineering contributors, and AI assistants working on Sports Today.

**When to update**  
Update when a major product track begins, changes scope, or reaches completion.

**Related documents**  
- `docs/product/VISION.md`
- `docs/product/ROADMAP.md`
- `docs/product/EXPERIENCE_PRINCIPLES.md`
- `docs/design/DESIGN_SYSTEM.md`
- `docs/engineering/ARCHITECTURE.md`
- `docs/engineering/DECISION_LOG.md`

---

# North Star

Sports Today should help answer three questions across the full sports day:

1. **What should I pay attention to before games begin?**
2. **What is happening now?**
3. **What did we learn after the games ended?**

The current product is strongest at the first question. The future roadmap should expand into the second and third without weakening the core preview experience.

This creates three distinct product modes:

- **Preview**
- **Live**
- **Postgame**

They should feel connected, but they should not be treated as the same feature.

---

# Product Track 1 — Live Scores and Live Game State

## Goal

Make the Today page reflect what is happening now.

This is the most immediate extension of the current schedule experience and should be treated separately from a full postgame product.

## Why it matters

A sports companion that shows only scheduled start times becomes less useful once games begin. The homepage should evolve naturally as the day progresses.

The product should move through:

```text
Upcoming → Live → Final
```

without requiring a separate app or workflow.

## Phase 1 — Final Scores

Add final score and final status to schedule cards.

Example:

```text
FINAL

Mets        3
Phillies    5
```

Requirements:

- retain away and home scores from source feeds
- normalize status across leagues
- preserve chronological order
- keep the game card clickable
- do not remove the preview page
- avoid building a recap experience yet

## Phase 2 — Live State

Add lightweight live details where source feeds support them.

Possible examples:

### MLB
- inning
- top/bottom
- outs
- score

### WNBA / NBA
- quarter
- game clock
- score
- halftime status

### MLS / Soccer
- match minute
- halftime
- score
- stoppage-time status where available

### NFL / NCAA Football
- quarter
- game clock
- possession if available
- score

## Phase 3 — Live Refresh Behavior

The UI should update without requiring a full manual restart.

Possible approaches:

- short cache TTL while games are live
- manual refresh control
- periodic rerun only when at least one game is live
- slower refresh cadence for final or scheduled games

Avoid aggressive polling when nothing is live.

## Product principle

Live state should be useful but compact.

Sports Today should not try to become a full play-by-play app. The homepage only needs enough information to answer:

> What is happening right now?

## Open questions

- How often should live cards refresh?
- Should final games remain mixed into the main slate or collapse into a Results section?
- Should live games float to the top, or remain chronological?
- Should score spoilers be optional later?

---

# Product Track 2 — Meaningful Postgame Experience

## Goal

Turn the preview into a learning loop.

The postgame experience should answer:

- What actually happened?
- Which pregame ideas were right?
- Which opportunities succeeded?
- What did the preview miss?
- What should we learn from this game?

## Why this is a separate track

Displaying a final score is a data-normalization and presentation task.

Building a meaningful postgame experience requires:

- grading logic
- result ingestion
- box-score or play-by-play context
- comparison against pregame claims
- editorial synthesis
- historical storage

This should be tackled much later and should not block final-score support.

## Future postgame page concept

### Final Result

- final score
- winner
- major performers
- game status

### How It Played Out

Compare actual game shape with pregame expectations.

Example:

```text
Expected:
Starter-driven, balanced game

Actual:
Philadelphia scored early and forced New York into bullpen innings
```

### Preview Check

Grade the major pregame ideas.

```text
✓ Phillies power mattered
✓ Scott generated strikeouts
✕ Mets recent-form edge did not carry over
```

### Opportunities Graded

Show whether each game-specific opportunity succeeded.

```text
Bryson Stott — 1+ Hit — WIN
Justin Crawford — 1+ Hit — LOSS
```

### What We Learned

A concise editorial takeaway generated from structured results.

## Long-term opportunity

Sports Today could become unusually trustworthy by showing not only what it predicted, but where it was wrong.

That creates a closed loop:

```text
Preview → Result → Grade → Learn → Improve
```

## Important constraint

Do not create a fake “accuracy” story from tiny samples.

All postgame evaluation should clearly communicate:

- sample size
- market type
- sport
- time period
- grading rules
- missing or void results

---

# Product Track 3 — Yesterday’s Results

## Goal

Create a dedicated page that grades the previous day’s Top Opportunities.

This is the bridge between the current preview product and the later full postgame experience.

## Core question

> How did yesterday’s opportunities perform?

## Recommended page structure

### Summary Header

```text
Yesterday’s Results

7 wins
3 losses
70% hit rate
```

Also show:

- total graded
- pending
- void / unavailable
- sport breakdown

### Opportunity Results

Each opportunity row should show:

- player
- team
- sport
- opportunity type
- original score
- result
- final grade
- supporting result detail

Example:

```text
Bryson Stott
1+ Hit
Score: 89
Result: 2-for-4
WIN
```

### By Sport

- MLB
- WNBA
- MLS
- NFL
- NCAA

### By Opportunity Type

- 1+ Hit
- 5+ Assists
- 8+ Rebounds
- pitcher strikeouts
- future soccer markets
- future football markets

## Grading terminology

Use unambiguous labels:

- **Win**
- **Loss**
- **Push**
- **Void**
- **Pending**
- **Unable to Grade**

Avoid vague labels such as “good” or “bad.”

## Data requirements

The snapshot system already stores pregame results and context. Yesterday’s Results will require:

- stable opportunity IDs
- game IDs
- player IDs
- opportunity type
- threshold
- original score
- slate date
- actual result
- grading status
- graded timestamp
- grading engine version

## Product thought

This page should be factual, not defensive.

Do not explain away misses. Show them clearly.

Trust improves when the product is willing to say:

> This one was wrong.

---

# Product Track 4 — Performance Over Time

## Goal

Create a long-term scorecard showing how Top Opportunities have performed.

This is not a leaderboard for individual players. It is a performance and calibration page for the Sports Today opportunity system.

## Core questions

- How often are Top Opportunities correct?
- Does performance differ by sport?
- Which opportunity types are strongest?
- Do higher opportunity scores actually perform better?
- Is the system improving over time?

## Recommended page sections

### Overall Performance

- graded opportunities
- wins
- losses
- hit rate
- pending
- void
- current streak
- trailing 7-day / 30-day / season performance

### By Sport

Example:

| Sport | Graded | Wins | Losses | Hit Rate |
|---|---:|---:|---:|---:|
| MLB | 120 | 82 | 38 | 68.3% |
| WNBA | 54 | 33 | 21 | 61.1% |

### By Opportunity Type

Example:

| Type | Graded | Hit Rate |
|---|---:|---:|
| 1+ Hit | 120 | 68.3% |
| 5+ Assists | 22 | 63.6% |
| 8+ Rebounds | 18 | 55.6% |

### By Score Band

This is one of the most important calibration views.

Example:

| Score Band | Graded | Hit Rate |
|---|---:|---:|
| 90–100 | 42 | 78.6% |
| 80–89 | 85 | 64.7% |
| 70–79 | 61 | 55.7% |

If higher scores do not correspond to better results, the scoring system needs recalibration.

### Trend Over Time

Possible views:

- rolling 7-day hit rate
- rolling 30-day hit rate
- cumulative hit rate
- performance by engine version

### Engine Version Comparison

Because snapshots store engine version, future changes can be evaluated honestly.

Example:

```text
Engine v1.2
64.3% over 280 graded opportunities

Engine v1.3
69.1% over 94 graded opportunities
```

## Important statistical cautions

Always show sample size.

Do not overinterpret:

- tiny market samples
- short hot streaks
- one league’s partial season
- mixed opportunity types with very different base rates

Where appropriate, include:

- confidence intervals
- minimum sample thresholds
- “insufficient sample” states

## Product thought

This page should feel like a report card, not a marketing page.

The purpose is not to prove the system is good.

The purpose is to reveal whether it is good.

---

# Product Track 5 — MLS

## Goal

Add MLS to the Today page and eventually create a soccer-specific matchup experience.

This is a high-priority expansion because Seattle Sounders fandom gives the product a real household use case.

## Phase 1 — Today Page Coverage

Support:

- schedule
- team names
- team crests
- start time
- venue
- broadcast
- live score
- final score
- match status

## Phase 2 — MLS Opportunities

Potential future opportunity types depend on available data.

Possible examples:

- 1+ shot on target
- 2+ shots
- anytime goal contribution
- goalkeeper saves
- team to score
- player passing thresholds

Do not choose markets before confirming reliable player-event and lineup data.

## Phase 3 — MLS Matchup Page

Soccer should not reuse the MLB page.

Its core question should be:

> What moments and spaces are likely to decide this match?

Possible sections:

- Team Identity
- Expected Match Shape
- Possession vs transition
- Pressing profile
- Chance creation
- Set-piece threat
- Defensive vulnerability
- Key player battles
- Players in form
- What to watch
- Match-deciding moments

## Sounders-specific opportunity

Because the household follows Seattle closely, future personalization could include:

- Sounders games pinned first
- Sounders-specific notification
- match reminders
- season record and form
- opponent scouting
- postgame grading

This should remain optional and not distort the universal product.

---

# Product Track 6 — NFL

## Goal

Add NFL schedule coverage first, then determine the right matchup depth.

## Phase 1 — Today Page Coverage

Support:

- schedule
- team logos
- kickoff time
- venue
- broadcast
- live score
- quarter and game clock
- final score

## Phase 2 — Opportunities

Potential future markets:

- passing yards
- rushing yards
- receiving yards
- receptions
- anytime touchdown
- quarterback passing touchdowns
- defensive sacks

These require reliable player availability, starters, injuries, and role context.

## Phase 3 — NFL Matchup Page

The core question should be:

> Which matchup creates the largest advantage?

Possible sections:

- offensive identity
- defensive identity
- trench matchup
- quarterback pressure
- explosive-play threat
- red-zone efficiency
- turnover risk
- key injuries
- players positioned to succeed
- expected game script

NFL matchup depth should wait until data reliability is strong enough to support injuries, starters, and role changes.

---

# Product Track 7 — NCAA Football and Basketball

## Goal

Add major NCAA games to the Today page without prematurely committing to deep matchup analysis.

## Recommended initial scope

Focus on:

- ranked teams
- major conferences
- nationally televised games
- rivalry games
- postseason / tournament games
- user-selected favorite teams

## Today Page Coverage

Support:

- matchup
- rankings where available
- logos
- start time
- broadcast
- live score
- game state
- final score

## Matchup-page caution

NCAA introduces significant complexity:

- huge number of teams
- inconsistent data quality
- player turnover
- lineup instability
- transfer portal
- injuries
- uneven schedule strength

A deep matchup page may be valuable later, but the first product win is simply:

> Show me the important college games today.

## Future possibilities

### NCAA Football
- ranked matchup context
- playoff implications
- rivalry history
- offensive/defensive identity
- quarterback matchup

### NCAA Basketball
- tournament implications
- pace
- shooting profile
- rebounding
- turnover pressure
- upset potential

---

# Shared Architecture for League Expansion

Each new league should follow the same broad sequence:

```text
1. Schedule coverage
2. Live and final score support
3. Opportunity types
4. Sport-specific matchup page
5. Postgame grading
6. Long-term performance tracking
```

A new league should not need all six before appearing in Sports Today.

The Today page should be allowed to support leagues at different maturity levels, provided the UI is honest about what is available.

## League maturity states

### Schedule Only
Shows games, times, and results.

### Analysis Available
Shows opportunities or matchup analysis.

### Full Preview
Has sport-specific matchup page.

### Grading Available
Opportunities can be evaluated after completion.

### Full Lifecycle
Preview, live, final, postgame, and historical performance are all connected.

---

# Recommended Implementation Order

## Near Term

1. Verify exact score/status fields from every current schedule source.
2. Extend `SlateGame` and schedule cache for score and live-status fields.
3. Build Final Score V1.
4. Build lightweight Live State V1.
5. Let MLB Phase 1 run across a full slate and collect feedback.

## Next

6. Build Yesterday’s Results data model and grading pipeline.
7. Grade existing MLB 1+ Hit and WNBA opportunity types.
8. Create Yesterday’s Results page.
9. Begin persistent performance aggregation.
10. Build Score Over Time page.

## League Expansion

11. Add MLS schedule/live/final support.
12. Add NFL schedule/live/final support.
13. Add targeted NCAA schedule coverage.
14. Design WNBA/NBA matchup page.
15. Design MLS matchup page.

## Later

16. Add new opportunity markets.
17. Add full postgame pages.
18. Compare pregame claims with actual results.
19. Add personalization, favorites, reminders, and Sounders-first options.

---

# Key Dependencies

## Live Scores depend on

- source status fields
- normalized score model
- cache freshness
- refresh behavior

## Yesterday’s Results depends on

- stable opportunity snapshots
- actual player results
- grading rules
- resolved game status

## Score Over Time depends on

- Yesterday’s Results
- persistent grading history
- opportunity type normalization
- engine version tracking

## Postgame Experience depends on

- final score
- box score or play-by-play
- graded opportunities
- stored pregame story and game-shape claims

## New League Opportunities depend on

- player-level data
- lineup or role context
- grading-capable result data

---

# Product Principles for All Future Tracks

## 1. Preview, live, and postgame are different jobs

Do not force one page or one data model to pretend they are identical.

## 2. Honest partial support is acceptable

A league may appear with schedule and scores before analysis exists.

## 3. Every opportunity must be gradeable

Do not add a new opportunity type without defining how it will be resolved.

## 4. Store what the product believed before the game

Snapshots should preserve:

- score
- evidence
- risk
- matchup context
- engine version
- data availability

Without that, postgame evaluation becomes unreliable.

## 5. Show misses as clearly as wins

Trust is more valuable than a flattering record.

## 6. Score calibration matters more than raw hit rate

A score of 95 should outperform a score of 75 over meaningful samples.

## 7. Each sport gets its own editorial lens

- Baseball: What kind of game will unfold?
- Basketball: Where will the game be won?
- Soccer: What moments and spaces will decide it?
- Football: Which matchups create the largest advantage?

## 8. The homepage stays universal

Schedules, live state, final scores, and opportunity cards should remain consistent even when matchup pages differ by sport.

---

# Definition of Success

Sports Today eventually supports the entire sports-day loop:

```text
Morning
Understand what matters

Before the game
Know what to expect

During the game
See what is happening

After the game
Understand what happened

The next day
See what was right and wrong

Over time
Know whether the system is actually improving
```

That is the product Sports Today is becoming.
