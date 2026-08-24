# The Visual Asset Playbook

A reusable process for reviewing a product's visual identity and commissioning, QA'ing, and landing new art assets. Distilled from The Long Game's 2026-08 redesign (three delivery rounds, one rejection round, zero assets wired in blind), written to apply to **any future project** — swap the museum specifics for whatever the project's world is.

The one-sentence version: **review against the written concept, decide before you commission, brief so a stranger could execute, QA before you wire, verify with your eyes, and feed every failure back into the rules.**

---

## Phase 0 — The grounded review

Before proposing anything, establish what *is*, in evidence, not impressions.

1. **Recover the concept contract.** Find the original design intent in writing (a concept doc, a brief, a CLAUDE.md, a pitch). This is the yardstick. If none exists, write one first and get it approved — you cannot diagnose drift from an unwritten standard.
   - *Here:* the "Museum, Lit Properly" concept explicitly said *thin* borders, warm light used *sparingly* — which is what made "big gold frames everywhere" diagnosable as drift rather than taste.
2. **Inventory what exists.** Every asset file (with sizes and dimensions), every style rule, every doc claiming status. Trust nothing that isn't verified: this project's asset README claimed "nothing unused" while the wordmark was orphaned and a "reference-only" texture was load-bearing in the nav.
3. **Look at the actual art.** Open the images. Read the SVG source. Screenshot the rendered pages. Reviews written from file names and doc claims miss everything that matters (near-black "well lit" rooms, placeholder text shipped in chrome, `currentColor` rendering invisible black).
4. **Review by layer, not by page.** Background imagery / surfaces & materials / lighting / typography / color / iconography / chrome & furniture / charts / layout rhythm / housekeeping. Each layer gets its own verdict. Page-by-page reviews find symptoms; layer reviews find systems.
5. **Diagnose root causes, and count things.** "Gold frames everywhere" traced to exactly two causes: one border-image applied by nine CSS rules, and lighting that never actually shipped. Numbers make drift undeniable — *31 uses of the gold variable; nine border-image rules; ~13 framed boxes on one screen; ~90% of each room canvas near-black.*
6. **Write two documents, not one:**
   - **The review + plan** — findings per layer, the phased remediation, and *measurable acceptance checks* (e.g. "≤2 ornate frames visible per viewport," "at 50% scroll the room must still read as a room").
   - **The assets brief** — see Phase 2. Keep it separate so it can be handed to the graphics team without any of the review's context.

## Phase 1 — The decision gate

Extract every question only the owner can answer, and ask them **before** anything is commissioned. Each question gets a recommendation and a note on exactly what it blocks.

- Good gate questions are cheap to answer and expensive to guess: *Is this placeholder-looking name actually the real name? Which direction of "well lit"? Does real photography exist? Is regeneration of existing art acceptable?*
- Record the answers somewhere durable the moment they arrive. They are the project's constitution; three rounds later nobody should re-litigate them.

## Phase 2 — The brief

Written so someone with **zero project context** can deliver correctly on the first pass.

Every asset request carries:

| Field | Why it exists |
|---|---|
| Purpose | What the asset does in the product — what it replaces, where it renders |
| Look | The art direction in prose, including mood words *and* concrete references |
| Format / dimensions | Exact — "2200×640 WebP," not "wide" |
| File-size ceiling | Stated up front. The one time this project skipped it, a 1.4MB texture shipped and had to be redone |
| Exact filename & path | Drop-in replacement discipline (Phase 3 depends on it) |
| Color source of truth | Point at the palette *in code*, never "match the existing look by eye" |
| Per-item callouts | The specific things QA will check ("the Arena carries a red-orange undertone," "fill the empty frames") — these become the QA checklist |

Plus, once per brief:

- **Global conventions** — naming keyed to the code's slug function, format rules, and every rule earned from a past failure (see Rules Bank).
- **Priority waves with explicit blockers** — what can start now, what waits on a decision, what's opportunistic.
- **Delivery-note requirements** — ask the artist to state recommended integration values (slice values, render sizes)… and treat them as suggestions to verify, not gospel (this project's recommended 3–4px frame width rendered sub-pixel; production needed 10px).

## Phase 3 — Implement everything that needs no assets, first

Never let code wait on art:

- Ship the full design change with **interim stand-ins** built from what exists (a CSS-only dark ledger held the tables' place for two days until the parchment texture arrived).
- Design integration points so deliveries are **drop-in**: same filenames, same dimensions, one `cp` and a rebuild.
- This phase also flushes out integration questions *before* the art exists (where does light-on-dark text recoloring live? does the frame need a stacking-context fix?) — cheaper to learn on a stand-in.

## Phase 4 — Delivery QA (the gate that earns its keep)

**Nothing gets wired in until it passes. Partial acceptance is normal.** A delivery is a set of independent items, each with its own verdict.

Three inspection levels, all mandatory — each has caught failures the others missed:

1. **Mechanical / spec** — dimensions, file sizes vs. ceilings, alpha channels where required, tile-seam checks, filename conventions. Scriptable; script it.
2. **Source-level** — open the files. Grep vector art for `<text>`, `font-family`, `currentColor` in non-inline contexts, duplicate/unprefixed IDs, dead defs, **and empty groups**. *The preview PNGs of the small medallions looked perfect while all 24 SVGs shipped with empty sigil groups — only source inspection caught it.*
3. **Eyes on the art** — render or view every piece, against the concept contract and the brief's per-item callouts. *The nameplate passed every mechanical check and was still unshippable: its "outlined lettering" was a blocky pixel font.*

Verdict discipline:

- **Accept** and install only what passes; delete rejected files from the working tree (never let them near production).
- **Reject in writing**, in the brief itself: what failed, the evidence, what correct looks like. Note when the *intent* was right and only the execution failed (preview proved the design existed; the export dropped it).
- **Find the systemic cause.** Three rejected item groups here traced to one broken text-outlining step — one root-cause note turns three redeliveries into one.

## Phase 5 — Wire in and verify with your eyes

- Install accepted assets to their final paths; remove delivery bundles entirely (a bundle dropped inside a served directory will ship as junk).
- Rebuild and **screenshot the real rendered product** — every affected surface, headless if needed. Look at the screenshots. Every round of this project's implementation had a defect that only a screenshot caught: a washed-out frame, a broken portrait image, seven ornate frames in one grid, emoji leaking in from the data layer.
- Iterate in the same session — integration values (frame widths, z-ordering, clip points) are almost never right on the first try, and they're one-line fixes when you're looking at the result.
- After deploy, verify **the live product**, not just local: assets return 200, the served CSS references the new files, the served HTML contains what you think it does. Expect CDN propagation lag before declaring failure.

## Phase 6 — The feedback loop

- Put it in front of the owner on the real product, early. Perceptual feedback ("the parchment reads very bright," "dark but not easier to read") is design data — **diagnose it to a mechanism** before fixing: the paper was emissive-bright against a dark field, and the recolor had collapsed hierarchy into uniform darkness rather than increasing contrast.
- Fix at the mechanism level (multiply the material down, rebuild the hierarchy with weight *and* tone), not by nudging one value until the complaint stops.
- **Promote every resolved complaint into a durable rule** (see below) so no future asset re-litigates it.
- Keep all status docs truthful as you go: the brief's status table, the asset-folder manifest, the review doc's status header. A doc that says "delivered" or "unused" must be verifiably true — stale claims cost a future session real time.

---

## The Rules Bank (seed for any new project, grown from failures here)

Every rule below was paid for. Start new projects with these; append the new project's own scars.

**Vector assets**
- No `<text>` elements with system font families — all lettering as real letterform outlines. And *pixel-font "outlines" are an automatic reject*: generated outlining must produce the actual letterforms.
- No `currentColor` in files consumed via `<img>` or CSS `background-image` — it can't inherit there and silently renders black. Reserve it for inlined SVG.
- Unique, asset-prefixed IDs; no dead defs/filters. Harmless as `<img>`, an ID-collision landmine the day something gets inlined.
- Grep for empty groups (`></g>`) — art can vanish in export while previews still look right.

**Raster assets**
- Size ceiling stated in the brief, enforced in QA.
- Tileables checked at 4× repeat; alpha verified programmatically when the use depends on it.
- Light-toned materials on a dark product must be *lit, not backlit* — target a dimmed rendered value (multiply/vignette in integration), and brief future paper-family assets to the dimmed target, not the bright ideal.

**Integration**
- Colors have one source of truth in code; art matches code, never the reverse, and never "by eye."
- Dark-on-light recoloring is a *hierarchy* job, not a darkness job: primary ink, weighted emphasis, distinctly lighter secondary — contrast comes from separation, not uniform darkness.
- Scope-level theming (CSS custom-property re-scoping on the container) beats per-element recolors — one block retints everything inside, forever.
- Verify artist-recommended integration values (slices, render widths) by render before adopting.
- Ornament is rationed by meaning: when a treatment marks *significance*, count how many instances one screen shows, and write the ceiling into acceptance checks.

**Process**
- Decisions before commissions; briefs a stranger can execute; QA before wiring; screenshots before "done"; live verification after deploy; failures promoted to rules.

---

## Artifact checklist (what exists when the process is healthy)

- [ ] Concept contract (approved, written)
- [ ] Review doc with per-layer findings, counted evidence, phased plan, measurable acceptance checks, and a status header kept current
- [ ] Decision record with owner answers
- [ ] Assets brief with per-item specs, global conventions, priority waves, and a living per-item status/verdict table
- [ ] Asset-folder manifest (README) that is verifiably true at all times
- [ ] Screenshot evidence per implementation round
- [ ] Rules bank, growing
