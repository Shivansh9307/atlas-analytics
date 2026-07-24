---
description: Re-run only the narrative wave against a run's validated findings.
argument-hint: <run_id>
---

Re-run the narrative (part of Wave E) for run **$ARGUMENTS**.

Read stored `findings.md` + `validation.md` + `provenance.json`. Spawn
`narrative-writer` to rewrite `narrative.md` in SCQA/pyramid form for the brief's
decision owner. Every number must carry a provenance ID that resolves in the
ledger (GATE 4 discipline).

Use after feedback on messaging without re-querying. Report the one-sentence answer
+ the path. If you changed which numbers are cited, re-check provenance before done.
