---
description: Rebuild the deck from a past run's stored findings (no re-query).
argument-hint: <run_id>
---

Rebuild the deck for run **$ARGUMENTS** from stored artefacts.

Read `runs/$ARGUMENTS/findings.md`, `narrative.md`, and `provenance.json`. Have
`deck-builder` reconstruct the `DeckSpec` and call `build_deck`. Do NOT re-query —
use the stored numbers and their provenance IDs.

GATE 4 still applies: every number on a slide must resolve in the ledger. Write
`runs/$ARGUMENTS/deck.pptx` + `speaker_notes.md`. Report slide count + paths.
