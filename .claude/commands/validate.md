---
description: Re-run the red-team validation on a past run (independent re-derivation + attacks).
argument-hint: <run_id>
---

Re-run validation for run **$ARGUMENTS**.

Spawn `red-team-validator`. It must NOT read the analyst's queries — it
independently re-derives the headline from raw sources with its own query and
compares within `TOLERANCES.rederivation_rel` (±0.5% default), then runs its
attack battery (filter leakage, survivorship, date-boundary, Simpson, alternative
explanations).

Report PASS/FAIL, the re-derived vs original numbers, and any surviving attacks
with their routing. Update `runs/$ARGUMENTS/validation.md`.
