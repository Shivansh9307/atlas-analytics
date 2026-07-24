---
name: deck-standards
description: Layout grid, chart selection, speaker-note structure, and appendix requirements for Atlas decks. Use when building or reviewing a .pptx.
---

# Deck standards

Builder: `atlas/lib/deck_pptx.py`. 16:9 (13.33×7.5in).

## Fixed skeleton (never reorder)
1. Title — a **claim** (see `narrative-craft`).
2. Key insight.
3..N Supporting evidence — **one chart per claim**.
N+1 So-what.
N+2 Recommendation.
Appendix: Methodology · Assumptions · Provenance table.

## Chart selection
| Claim shape | Chart |
|---|---|
| Level change over 2–N periods | column (few) / line (many) |
| Contribution / breakdown | bar (horizontal), sorted by magnitude |
| Part-to-whole (≤5 parts, one period) | stacked bar — avoid pie |
No chart junk: no 3-D, no gratuitous gridlines, legend only when >1 series, title
only when it adds meaning. See `dataviz` skill for palette/accessibility.

## Speaker notes
Every slide: 60–90 seconds spoken (~130–200 words). Structure: restate the claim →
the one number that proves it → the "so what" for the owner. Written to
`speaker_notes.md` too.

## Appendix (required)
- Methodology: how numbers were derived + the re-derivation tolerance.
- Assumptions: every declared assumption from the brief.
- Provenance: claim → value → query_hash → evidence tier. GATE 4 blocks export if
  any slide number is missing from the ledger.
