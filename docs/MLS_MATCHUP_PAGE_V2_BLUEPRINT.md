# MLS_MATCHUP_PAGE_V2_BLUEPRINT

> **Status:** Draft v2\
> **Purpose:** Definitive implementation blueprint for the MLS Matchup
> Page.

------------------------------------------------------------------------

# Design North Star

The MLS Matchup Page should answer one question better than any other
sports page in Sports Hub:

> **"What kind of match am I about to watch?"**

The page is not a box score, database, or betting sheet.

It is an explanation engine.

------------------------------------------------------------------------

# User Journey

## 5 seconds

The user knows: - who is playing - where - when - current status

## 15 seconds

The user knows: - which team has been stronger - which team is at home -
who the important players are

## 30 seconds

The user understands: - tactical identities - expected game flow -
likely decisive moments

## After the match

The user should recognize the patterns they were told to watch.

------------------------------------------------------------------------

# Information Hierarchy

1.  Hero
2.  Matchup Snapshot
3.  Tactical Matchup ⭐
4.  Key Storylines
5.  Projected Lineups
6.  Players to Watch
7.  Attacking Profiles
8.  Discipline
9.  What To Watch Timeline ⭐
10. Honest Gaps
11. Data Context

No section should appear simply because data exists.

------------------------------------------------------------------------

# Tactical Matchup (Signature Section)

This is the emotional center of the page.

It should compare:

-   Possession preference
-   Pressing style
-   Defensive line
-   Width
-   Transition speed
-   Set-piece danger
-   Crossing tendency
-   Directness
-   Game control

Display each as:

-   Home advantage
-   Even
-   Away advantage

Every row includes one sentence explaining *why*.

Example:

> Seattle presses high after turnovers, while LA Galaxy are most
> dangerous attacking quickly into open space.

------------------------------------------------------------------------

# Team Identity Cards

Every club should gradually earn a stable identity.

Example categories:

-   Possession Team
-   Counterattacking Team
-   High Press
-   Low Block
-   Set Piece Specialists
-   Crossing Team
-   Direct Attack
-   Patient Build-up

These labels should emerge from data rather than editorial assignment.

------------------------------------------------------------------------

# Matchup Snapshot

Maximum of 8 metrics.

Preferred:

-   Goals / Match
-   Goals Allowed
-   Goal Difference
-   Shots
-   Shots on Target
-   Possession
-   Passing Accuracy
-   Last Five Form

No more than eight.

Less is better.

------------------------------------------------------------------------

# Storyline Rules

Storylines must be deterministic.

Examples:

-   Home Fortress
-   Road Struggles
-   Set Piece Edge
-   Hot Goalkeeper
-   Finishing Regression
-   Derby Match
-   Fixture Congestion
-   Playoff Pressure

Every storyline should include:

-   Trigger
-   Evidence
-   Confidence

------------------------------------------------------------------------

# Projected Lineups

Pitch visualization.

Status badge:

-   Projected
-   Confirmed
-   Unavailable

Unavailable players should remain visible outside the pitch rather than
silently disappearing.

------------------------------------------------------------------------

# Players to Watch

Never simply choose the leading scorer.

Choose players who matter to *this* matchup.

Potential archetypes:

-   Finisher
-   Creator
-   Ball Progressor
-   Defensive Anchor
-   Goalkeeper

------------------------------------------------------------------------

# What To Watch Timeline

One of the signature Sports Hub features.

Structure:

Pregame

↓

Opening 15'

↓

Expected Midfield Battle

↓

Key Tactical Shift

↓

Late Match Factors

↓

Substitution Impact

Each point explains something the viewer should notice during the
broadcast.

------------------------------------------------------------------------

# Honest Gaps

Never hide uncertainty.

Possible messages:

-   Lineups not confirmed.
-   Small sample size.
-   Missing advanced tracking.
-   Player recently returned from injury.
-   Tactical model confidence is low.

Honesty builds trust.

------------------------------------------------------------------------

# Progressive Soccer Intelligence

## Version 1

Rule-based.

## Version 1.5

Opponent-aware.

## Version 2

Formation-aware.

## Version 3

Live tactical adaptation.

The page layout never changes.

Only the intelligence improves.

------------------------------------------------------------------------

# Visual Language

Reuse Sports Today.

Global:

-   charcoal
-   orange
-   subtle borders

Team-specific:

-   primary colors only where comparing teams

Avoid visual clutter.

------------------------------------------------------------------------

# Component Reuse

Reuse:

-   hero shell
-   section container
-   navigation
-   comparison rows
-   player cards
-   provenance footer

Create new:

-   tactical matchup
-   pitch diagram
-   W/D/L dots
-   attacking profile
-   timeline
-   team identity model

------------------------------------------------------------------------

# V1 Scope

Must ship:

✓ Hero

✓ Snapshot

✓ Tactical Matchup

✓ Storylines

✓ Players to Watch

✓ Honest Gaps

May ship later:

-   xG
-   Passing networks
-   Heat maps
-   Live win probability
-   Advanced tactical overlays

------------------------------------------------------------------------

# Success Test

If someone unfamiliar with either club watches the match after reading
this page, they should repeatedly think:

> "That's exactly what the page said to watch."

If that happens, the page succeeded.
