# Sports Hub --- WNBA Matchup Page Specification (v2)

## Vision

The WNBA matchup page is the basketball counterpart to the MLB matchup
page, but it should be designed around **how basketball works**, not by
translating baseball concepts.

The page should answer, in order:

1.  **What kind of game is this likely to be?**
2.  **Why?**
3.  **Where will the game be won or lost?**
4.  **Which players will shape the outcome?**
5.  **What has changed recently?**
6.  **What are the strongest player opportunities?**

Every section should contribute to telling a coherent story.

------------------------------------------------------------------------

# Core Principles

-   Tell a basketball story rather than presenting disconnected
    statistics.
-   Never imply certainty that the data cannot support.
-   Explain *why* numbers matter.
-   Prefer comparisons over isolated values.
-   Every section should answer a user question.
-   Every metric must have a clear source and fallback.

------------------------------------------------------------------------

# Recommended Page Flow

## 1. Hero

Purpose: Immediately orient the user.

Display:

-   Team logos
-   Team names
-   Records
-   Date / time / venue
-   Home / away
-   Featured player for each team
-   Season series (if available)

Future: - Odds (optional)

------------------------------------------------------------------------

## 2. Game Script (Executive Summary)

One automatically generated paragraph.

Examples:

-   Fast-paced offensive matchup
-   Defensive battle
-   Clash of contrasting styles
-   Paint-oriented game
-   Perimeter-heavy game

The Game Script should summarize the matchup using supporting statistics
but remain readable.

This becomes the first thing users read.

------------------------------------------------------------------------

## 3. Game Snapshot

Quick-glance information.

Suggested cards:

-   Last 5 record
-   Current streak
-   Last 5 scoring
-   Last 5 defense
-   Home/Road record
-   Rest days
-   Season series

Purpose:

"How are these teams entering tonight?"

------------------------------------------------------------------------

## 4. Team Identity

Instead of listing statistics, define each team's identity.

Possible labels:

-   Elite offense
-   Defensive-minded
-   Three-point shooting
-   Transition team
-   Paint-first offense
-   Ball movement
-   Rebounding
-   Rim protection

Support each identity with statistics.

------------------------------------------------------------------------

## 5. Where the Game Will Be Won

This replaces a generic matchup table.

Create 3--5 "battlefields."

Examples:

### Tempo

Who benefits from a fast game?

### Paint

Interior scoring versus rim protection.

### Perimeter

Three-point offense versus perimeter defense.

### Turnovers

Ball security versus defensive pressure.

### Rebounding

Second-chance opportunities.

Each battle includes:

-   short explanation
-   supporting statistics
-   slight advantage indicator (if supported)

------------------------------------------------------------------------

## 6. Players Who Shape Tonight

Not defensive assignments.

Highlight players whose impact is expected to define the game.

Categories may include:

-   Superstar
-   Primary scorer
-   Primary creator
-   Defensive anchor
-   Floor spacer
-   Rebounding presence

Each player card should include:

-   season averages
-   recent trend
-   strengths
-   why they matter tonight

------------------------------------------------------------------------

## 7. Trending Players

Separate from star players.

Identify players whose recent performance differs from season baseline.

Categories:

Trending Up

Trending Down

Potential Breakout

Expanded Role

Recent Slump

Base trends on objective changes.

------------------------------------------------------------------------

## 8. Team Trends

Visual trend section.

Possible sparklines:

-   Points
-   Opponent points
-   FG%
-   3PT%
-   Rebounds
-   Turnovers

Purpose:

Allow users to recognize momentum visually.

------------------------------------------------------------------------

## 9. Opportunity Engine

Reuse the existing Sports Hub opportunity system.

Cards contain:

-   Player
-   Market
-   Confidence
-   Supporting evidence
-   Counter evidence

This should be the culmination of everything above.

------------------------------------------------------------------------

# Data Available Today

Current data supports:

-   Schedule
-   Player game logs
-   Team aggregation
-   Recent trends
-   Team statistical comparison
-   Season series (current dataset)
-   Opportunity engine

------------------------------------------------------------------------

# Honest Limitations

Current version should avoid:

-   Claimed defensive assignments
-   Unsupported injury assumptions
-   Unsourced betting recommendations

Missing information should display graceful empty states.

------------------------------------------------------------------------

# Future Data Roadmap

## High Priority

-   Injury feed
-   Expected starters
-   Rest/travel
-   Possession estimates
-   Offensive Rating
-   Defensive Rating
-   Net Rating
-   Pace

## Medium Priority

-   Multi-season head-to-head
-   Minutes trends
-   Rotation stability
-   Usage trends
-   Opponent shot profile

## Long-Term

-   Tracking data
-   Defensive matchup data
-   Sportsbook markets
-   Live probability models

------------------------------------------------------------------------

# Engineering Guidance

-   Separate computation from presentation.
-   Build reusable basketball aggregation functions.
-   Shared components should support future NBA implementation.
-   Every card should tolerate partial data.
-   All calculations should expose provenance.

------------------------------------------------------------------------

# Success Criteria

A user finishing the page should understand:

-   the expected style of game,
-   each team's strengths,
-   the critical battles,
-   the players most likely to influence the outcome,
-   the recent trends,
-   and why the opportunity engine favors particular player markets.

The page should feel like reading a concise, intelligent basketball
preview---not a dashboard full of disconnected numbers.
