# Design System

> **Purpose** — The visual language of Sports Today: color, type, spacing, radius, shadow, motion, and how components should look and feel.
> **Audience** — Anyone touching UI (`styles/app.css`, `components/`, `web/templates/`) — humans and AI.
> **Update when** — A visual token or component treatment changes. The implementation of record is `styles/app.css`; keep this document aligned with it.
> **Related** — [Experience Principles](../product/EXPERIENCE_PRINCIPLES.md) · [Vision](../product/VISION.md) · [Architecture](../engineering/ARCHITECTURE.md) · [Docs index](../README.md)

> **Source of truth:** the running system is `styles/app.css` (one token-driven
> stylesheet). This document explains intent; when the two disagree, the CSS wins
> and this file should be corrected.

---

# Philosophy

Sports Today should feel like a premium sports application—not a data dashboard.

The goal is to make checking today's slate feel enjoyable.

Every screen should answer:

> "What should I pay attention to today?"

The app should feel calm, confident, and intentional.

Never busy.

Never overwhelming.

Never corporate.

---

# Design Inspiration

Primary inspiration:

- Apple Sports
- Flighty
- Linear
- Arc Browser
- Apple Wallet
- Notion Calendar

Secondary inspiration:

- Sofa
- Ivory
- Gentler Streak

Avoid visual inspiration from:

- Tableau
- Power BI
- Bootstrap
- Material dashboards
- Fantasy sports websites
- Sports betting sites

---

## Evolution Philosophy

Sports Today evolves through refinement, not reinvention.

Users should rarely feel like they need to relearn the interface.

Every release should feel like:

iOS 17 → iOS 18

not

Windows XP → Windows Vista.

When improving the application:

1. Preserve successful layouts.
2. Improve craftsmanship before changing structure.
3. Improve typography before increasing size.
4. Improve hierarchy before adding information.
5. Remove clutter before adding features.

If a redesign increases cognitive load or vertical space without increasing user value, reconsider the change.

Premium products are recognizable from one version to the next.

# Core Principles

## 1. Clarity over Density

Every screen should be immediately understandable.

Users should never need to search for the important information.

Hierarchy should naturally guide the eye.

---

## 2. Calm Confidence

Dark mode should feel warm rather than harsh.

Avoid excessive contrast.

Whitespace is a feature.

---

## 3. Premium Feel

Every interaction should feel intentional.

Buttons should feel tactile.

Cards should feel layered.

Motion should be subtle.

---

## 4. One Design Language

No page should look like it belongs to another application.

Every page should feel related.

---

# Brand Personality

Knowledgeable

Calm

Modern

Confident

Helpful

Never loud.

Never flashy.

Never "sports bar."

---

# Color System

## Primary

Sports Today Orange

Used for **two things only** — selection and opportunity identity:

- the accent word in the hero title (e.g. "Today's" — the rest of the title is white)
- **selection**: active segmented-control side, selected filter pills, active threshold
- **opportunity identity**: the score numerals + their outline

Explicitly **not** orange (so the accent doesn't compete on a dense screen): the
market line (neutral), secondary navigation (neutral until hover), and body/metadata.
Orange should attract attention naturally. Do not overuse — on the opportunity
screen especially, repeated orange on markets/nav/score at once reads as a toolbar,
not curation.

---

## Success

Green

Only used for:

- positive evidence
- confidence
- improvements

---

## Warning

Muted Coral

Only used for:

- risk
- uncertainty
- injury concerns

---

## Neutral

Everything else should be grayscale.

Avoid introducing new accent colors.

---

## The evidence threshold

Green means *positive evidence*, not *a positive number*. On an analysis surface those are
not the same thing, and treating them as the same is how a diagnostic turns into a
scoreboard.

So a difference is only tinted once it is large enough to be evidence. On Performance the
band is **±2 percentage points**: inside it, a figure stays grey no matter which side of
zero it falls. A `+0.4` rendered green asserts an edge the number cannot carry, and that
page is read for exactly that distinction.

The same restraint governs the market-pulse heatmap: low saturation, and the cells fade
with age, because eight equally-lit columns make ordinary variance look like a row of
findings.

---

# Typography

Typography creates hierarchy.

Never rely on color alone.

## Hero

Used once per page.

Example:

Today's Sports Slate

Large.

Bold.

Confident.

---

## Header restraint

The homepage header is intentionally just the **hero title + the Today/Tomorrow
segmented control** — nothing else. A date subtitle and per-league game-count
chips were tried and deliberately removed: they added information the header did
not need and grew its height. The header's job is to name the day and let the
user switch it, not to summarize the slate. Treat added header metadata as a
regression unless it clearly earns its space. (See "Refine before redesign".)

---

## Section Titles

Examples:

Top Opportunities

Today's Games

Player Profile

Large enough to anchor a section.

---

## Card Titles

Player names

Team names

Opportunity names

Strong weight.

Easy to scan.

---

## Metadata

Venue

Broadcast

League

Status

Muted.

Never compete with primary content.

---

# Spacing

Whitespace is intentional.

Crowding reduces confidence.

Major sections should breathe.

Cards should have generous internal padding.

Avoid stacking components tightly.

---

# Border Radius

Use one consistent radius scale.

Small

Medium

Large

Extra Large

The segmented control should define the standard.

---

# Shadows

Three elevation levels.

Small

Medium

Large

Cards should lift slightly on hover.

Never use dramatic shadows.

---

# Borders

Prefer:

spacing

background contrast

shadow

instead of borders.

Borders should be subtle.

---

# Motion

Motion communicates quality.

Allowed:

hover lift

fade

soft transitions

segmented control animation

button hover

Not allowed:

bouncing

elastic

overshoot

large transforms

---

# Cards

Cards are the foundation of the application.

Every card should have:

clear hierarchy

comfortable spacing

minimal visual noise

consistent radius

consistent shadow

consistent padding

---

# Match Cards

Visual priority:

League

↓

Teams

↓

Time

↓

Venue

↓

Broadcast

↓

Action

The eye should naturally follow this order.

---

# Opportunity Cards

Visual priority:

Opportunity Score

↓

Player

↓

Market (the opportunity, e.g. "15+ Points")

↓

Evidence

↓

Risk

The score badge should be immediately recognizable. Evidence should always feel
at least as prominent as risk. ("Opportunity Score" is the product's term — a
transparent, inspectable score, **not** a probability. See the glossary in
[Architecture](../engineering/ARCHITECTURE.md).)

---

# Analysis Surfaces

Daily Results and Performance carry more numbers than any other screen, and the risk is
that they read as a data dashboard — the thing this product is explicitly not. Three rules
keep them on the right side of that line.

## Conclusions above evidence

A page of ten tables of equal weight makes the reader assemble the verdict. Instead, each
surface **states its answer above the table that backs it**, and the page is banded into
levels separated by space and a small labelled rule:

1. **Conclusions** — the generated read, the headline figures, the verdict
2. **Primary evidence** — the diagnostics a reader would check the verdict against
3. **Deep diagnostics** — everything else, headings a step quieter

Space goes *between* the bands. Tables stay dense: the fix for a crowded page is hierarchy,
not padding.

## The headline is never a raw rate alone

A hit rate is a property of the props served as much as of the picking. Wherever one is
shown large, **the lift over baseline is shown at the same size, in the same card**, with
the base rate named underneath. The two are a pair; a layout that makes one a footnote to
the other is a regression, however good it looks.

Sample size is a headline too, never a footnote. A figure under the minimum sample sorts
*last*, renders quieted, and carries a badge — sorting alone is not enough, because the
biggest number on the page still reads as the ranking even when it sits at the bottom.

## Generated sentences look like sentences

The synthesized reads — signal check, "what this means", the calibration conclusion — are
prose in a card, not a stat tile. They get a brand-coloured left edge to carry headline
weight, a small uppercase label per observation, and body-sized type. They are allowed to
say nothing at all when the data does not support a claim.

## Components

Listed under the surface that owns them. The two pages share the three rules above; they
do **not** share parts, and the tiles are the trap — Performance leads with hit rate ·
lift · sample, Daily Results with record · hit rate · average score. Same shape, different
claim.

### Performance

| Pattern | What it is | Rule it carries |
|---|---|---|
| **Signal check** | 2–3 labelled observations in a brand-edged card | A category is omitted when there is nothing to say; never padded to three |
| **Period summary tiles** | Hit rate · lift vs baseline · sample, three equal tiles | Equal size is the point; the lift tile is the only one allowed a tint |
| **Trust board** | Tiered chips, one 3px coloured left edge per tier | Empty tiers are dropped — an empty "Strong signal" reads as a finding |
| **Calibration bars** | Bar = observed rate, tick = that band's base rate | The visible gap *is* the lift; no line is drawn between bands, because a line asserts a continuity the sample cannot support |
| **Sparkline** | Unlabelled, unscaled shape beside a table | A shape, not a chart. The table holds every number |
| **Filter chips** | "Filtered to …", each clearing only itself | Every figure below responds to them, and a reader who has scrolled has no other cue |

### Daily Results

| Pattern | What it is | Rule it carries |
|---|---|---|
| **Day scorecard** | Record · hit rate · average score as three large tiles, over a quiet inline strip of graded / void / pending | Three metrics answer "how did we do", the strip answers "on how much". Six equal tiles asked the reader to weigh a void count against a hit rate |
| **Comparison line** | One line under the scorecard: the day's rate, its delta against the trailing 30 days, then the lift over base beside it | Both scales or neither — the raw delta alone credits the picking for an easy slate. Colour only past 3 points, and only when the window has enough graded props to be a comparison |
| **Daily read** | 1–3 bullets, each a bolded verdict then the figure behind it | Gated on sample *and* on size; a day with nothing to say says nothing. Never padded to three, never a forecast |
| **Highest-scored misses** | Up to 3 misses drawn from the day's ten strongest predictions, in a coral-edged card | Never the widest numerical gaps — the question is whether the top of the scale means what it claims, and the sample has to be "the ones we were surest about" |
| **Audit row** | One prediction per row: result · player · prediction · score · actual, aligned to a heading row | Dense on purpose — these are two hundred rows to scan, not two hundred cards. The market is muted and the posted line carries the row; misses take a little more weight than hits. On phones the headings go and each number labels itself |
| **List controls** | Result pills with live counts, plus market / sort / view selects | Client-side, and `hidden` until their script runs: the export is bounded to `?date=`, and an inert control is worse than no control. A pill that would select nothing is not offered |
| **Score note** | A small `i` beside every score and score average | "Opportunity Score, never probability" is a product rule, so it travels with the number rather than living only in the small print |

---

# Buttons

Primary

Orange

Used sparingly.

Secondary

Neutral

Outlined or soft filled.

Pills

Rounded.

Compact.

Used for filters.

Segmented Controls

Highest quality control in the application.

Used whenever mutually exclusive options exist.

Example:

Today | Tomorrow

This control defines the visual language for all other controls.

---

# Icons

Icons should support text.

Never replace text.

Use consistent sizing.

Avoid mixing icon styles.

---

# Logos

League and team logos should be treated as first-class visual elements.

They should never feel like tiny afterthoughts.

Maintain consistent sizing.

Never distort.

---

# Information Density

The application should feel information-rich without feeling crowded.

If two pieces of information compete, one should become quieter.

Hierarchy is more important than quantity.

---

# Responsive Design

Desktop is the primary experience.

Tablet should retain the same hierarchy.

Mobile should stack gracefully without changing the design language.

A stacked track is `minmax(0, 1fr)`, never a bare `1fr`. A bare `1fr` cannot shrink below
its widest card's min-content width, and a card full of `white-space: nowrap` runs has a
min-content of a whole line — one long string then widens every card on the page past the
edge of the screen. Where a line genuinely cannot hold its content, prefer giving it a
second line over an ellipsis that deletes the information.

---

# Future Screens

Every new page should answer:

What is today's story?

Examples:

Today's Slate

Player Profile

Team Profile

Game Preview

Historical Trends

Everything should feel like another page in the same application.

---

# Animation Philosophy

Animations should be noticed emotionally rather than consciously.

Users should feel polish.

They should not notice animations.

---

# Accessibility

Maintain strong contrast.

Large click targets.

Readable typography.

Never communicate meaning through color alone.

---

# Things We Never Do

Heavy gradients everywhere

Neon colors

Complex backgrounds

Overlapping cards

Tiny text

Excessive borders

Dashboard widgets

Blinking animations

Visual clutter

---

# Definition of Success

When someone opens Sports Today they should immediately think:

"This feels like a polished sports application."

Not

"This feels like a dashboard someone generated."

Every design decision should move the application toward that goal.