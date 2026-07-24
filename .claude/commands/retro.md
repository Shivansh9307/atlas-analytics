---
description: Force a retrospective on a past run — write deduplicated lessons and promote repeats.
argument-hint: <run_id>
---

Force a retrospective for run **$ARGUMENTS**.

Spawn `retrospective-agent`. It diffs mid-flight corrections, detects the mistake
classes (validation rejections, query errors/retries, human corrections, repeated
clarifications → stored default), writes deduplicated lessons to
`memory/lessons.jsonl`, and promotes any twice-fired lesson to a hard artefact.

Report the lessons written, any promotions, and update `runs/$ARGUMENTS/retro.md`.
