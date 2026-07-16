# Experience Principles

> **Purpose** — The UX constitution: how every Sports Today screen should feel and behave. This governs interaction and information design; visual tokens live in the Design System.
> **Audience** — Anyone designing or building a screen — humans and AI.
> **Update when** — A screen-level interaction principle changes. New screens should be checked against this document before they ship.
> **Related** — [Vision](VISION.md) · [Design System](../design/DESIGN_SYSTEM.md) · [Roadmap](ROADMAP.md) · [Docs index](../README.md)

---

Sports Today is **a daily sports companion, not a dashboard.** Every screen should
help the user understand **what matters today** in under a minute. These
principles are how we hold that line at the level of a single screen.

---

## 1. One hero per screen

Every screen has exactly one thing it is primarily about, and it is unmistakable.
The homepage hero is the day's slate; a game screen's hero is the matchup. If two
elements compete to be the hero, one must become quieter. Never open a screen with
a wall of equally-weighted information.

## 2. Information hierarchy does the work

The user should never *search* a screen for what matters — hierarchy should walk
their eye to it. Establish rank with size, weight, spacing, and restraint, not
with boxes and borders. On an opportunity card the eye should flow **Score →
Player → Market → Evidence → Risk** without effort.

## 3. Tell a story; statistics are supporting cast

Lead with the "so what," not the number. Prefer "one of today's best rebounding
opportunities" over "7.3 rebounds per game." Every statistic on screen should
answer *"so what?"* — if it can't, it doesn't belong there.

## 4. Reduce cognitive load — curate, don't dump

Showing everything is easy and unhelpful. Decide what deserves attention and show
that. When a screen feels crowded, **remove information — don't shrink it.** The
absence of noise is a feature the user feels even if they can't name it.

## 5. Progressive disclosure

Surface the summary first; reveal detail on intent. The homepage shows the ranked
opportunity and its headline evidence; the game screen and expanders reveal the
deeper "why." Depth is always available, never in the way. Each level answers one
more "why?" than the last.

## 6. Trust through honesty

Never overstate confidence or hide uncertainty. Evidence is always visible, and
**negative evidence is at least as prominent as supporting evidence.** When data
is missing, stale, or cached, say so plainly (see degraded mode) rather than
presenting it as fresh. Trust is the product's most valuable feature.

## 7. Premium, quiet interactions

Motion communicates quality and should be felt, not noticed: subtle hover lift,
soft transitions, the segmented control's smooth switch. No bouncing, no
overshoot, no flashy reveals. Controls feel tactile; the app feels calm and
intentional, never loud or "sports bar."

## 8. Refinement over redesign

Successful layouts **evolve; they are not replaced.** Improve typography, spacing,
hierarchy, and craftsmanship before changing structure. A release should feel like
iOS 17 → iOS 18 — recognizably the same product, quietly better. A change that
adds cognitive load or vertical space without adding user value is a regression.
(This principle earned its own [decision-log entry](../engineering/DECISION_LOG.md)
after a redesign pass drifted too far and was reeled back.)

## 9. Everything I want, nothing I don't

The ideal screen contains exactly what the user needs for the moment it serves —
no ornamental metadata, no widgets added "because we can." Before adding anything,
ask: *would the user miss this if it disappeared?* If not, leave it out. Every new
element should ideally **replace** something, not accrete on top of it.

---

## The screen checklist

Before a screen ships, it should pass all of these:

- [ ] There is exactly **one hero**, and it's obvious.
- [ ] The eye reaches the most important thing **without searching**.
- [ ] Nothing on screen fails the **"so what?"** test.
- [ ] Detail is available through **progressive disclosure**, not crammed in.
- [ ] Uncertainty and data freshness are shown **honestly**.
- [ ] Interactions feel **calm and premium**; motion is subtle.
- [ ] The change **refined** rather than redesigned; density was preserved.
- [ ] Every element earns its place — **nothing the user wouldn't miss.**
