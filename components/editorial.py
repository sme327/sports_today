"""Rendering for editorial signals — the curation shown for leagues with no props.

Pure HTML over the shared evidence primitives (``op-evidence`` and friends), so a
schedule-only league looks like the rest of the product rather than a bolt-on.

The caveats render in the same block size and typography as the supporting evidence,
never smaller or dimmer, because "negative evidence is at least as prominent as
supporting evidence" is a product rule and this module is the easiest place to quietly
break it — the signals are the interesting part and the caveats are what keep them
honest.
"""

from __future__ import annotations

from html import escape

from components.icons import icon
from services.editorial import GameInterest


def _block(kind: str, heading: str, body: str) -> str:
    ic = icon("positive") if kind == "good" else icon("neutral") if kind == "flat" else icon("risk")
    return (f'<div class="op-evidence op-{kind}">'
            f'<div class="op-ev-head">{ic}<span>{escape(heading)}</span></div>'
            f'<div class="op-ev-body">{escape(body)}</div></div>')


def _caveat_block(items: list[str]) -> str:
    """Every caveat in one block, not one block each.

    They all carry the same heading, so rendering them separately stacked five identical
    "Worth knowing" headings down a phone screen — the repeated label became the loudest
    thing in the section, and the reader has to scan past it five times to find the five
    different sentences underneath.
    """
    ic = icon("neutral")
    body = "".join(f"<li>{escape(text)}</li>" for text in items)
    return ('<div class="op-evidence op-flat">'
            f'<div class="op-ev-head">{ic}<span>Worth knowing</span></div>'
            f'<ul class="op-ev-list">{body}</ul></div>')


def _chips(detail: GameInterest) -> str:
    chips = "".join(f'<span class="ed-chip">{escape(s.label)}</span>'
                    for s in detail.signals)
    return f'<div class="ed-chips">{chips}</div>' if chips else ""


def editorial_html(detail: GameInterest) -> str:
    """The full read on a game: what stands out, the evidence, and the caveats.

    Returns "" when there is nothing honest to say, so the caller can fall back to an
    explicit empty state instead of rendering a hollow section.
    """
    if not detail.signals:
        return ""

    lead = detail.signals[0]
    rest = detail.signals[1:]

    body = [f'<div class="ed-lead">{escape(lead.detail)}</div>', _chips(detail)]

    blocks: list[str] = []
    # Evidence from every signal, not just the lead: a rank-based lead carries only
    # "#1 Ohio State", while the records that matter come from the quality signals.
    evidence: list[str] = []
    for s in detail.signals:
        for item in s.evidence:
            if item not in evidence:
                evidence.append(item)
    # A signal that gets its own block below states its own case. Repeating that text
    # inside "Going in" made the first block a run-on of everything that followed it.
    detailed = [s.detail for s in rest
                if s.detail and s.kind not in {"conference", "postseason"}]
    evidence = [e for e in evidence if not any(e in d for d in detailed)]
    if evidence:
        blocks.append(_block("good", "Going in", " · ".join(evidence)))
    for s in rest:
        if s.detail and s.kind not in {"conference", "postseason"}:
            blocks.append(_block("good", s.label, s.detail))

    # Caveats last but not least — same block treatment as the evidence above.
    seen: set[str] = set()
    caveats: list[str] = []
    for text in list(lead.caveats) + [c for s in rest for c in s.caveats] + list(detail.caveats):
        if text in seen:
            continue
        seen.add(text)
        caveats.append(text)
    if caveats:
        blocks.append(_caveat_block(caveats))

    body.append(f'<div class="ed-grid">{"".join(blocks)}</div>')
    return (
        '<div class="mlb-section ed-section">'
        '<div class="mlb-section-head"><h2>The read</h2></div>'
        f'{"".join(body)}</div>'
    )


def editorial_empty_html(league: str, reason: str) -> str:
    """An honest empty state: say what is missing and why, never imply analysis."""
    return (
        '<div class="mlb-section ed-section">'
        '<div class="mlb-section-head"><h2>The read</h2></div>'
        f'<div class="ed-grid">{_block("flat", f"No read for this {escape(league)} game", reason)}</div>'
        '</div>'
    )
