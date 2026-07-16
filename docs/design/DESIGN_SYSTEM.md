# Design System

> **Purpose** — The visual language of Sports Today: color, type, spacing, radius, shadow, motion, and how components should look and feel.
> **Audience** — Anyone touching UI (`styles/app.css`, `components/`, `views/`) — humans and AI.
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

Used for:

- the accent word in the hero title (e.g. "Today's" — the rest of the title is white)
- selected controls (active segmented-control side, selected filter pills)
- opportunity score numerals and the market line
- highlights and active state

Orange should attract attention naturally. Do not overuse — the title itself is
white so the orange accent word carries the brand without shouting.

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

"This feels like a Streamlit app."

Every design decision should move the application toward that goal.