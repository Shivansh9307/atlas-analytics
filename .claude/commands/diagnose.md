---
description: Re-run only the diagnosis wave (root-cause + statistician) against stored evidence.
argument-hint: <run_id>
---

Re-run diagnosis (Wave D) for run **$ARGUMENTS**.

Read stored `hypotheses.md` + `evidence/`. Spawn `root-cause-analyst` then
`statistician`. Re-decompose, re-rank by share of delta, re-test significance/power,
re-run the Simpson check. Overwrite `findings.md`.

Use after giving feedback on the causal logic, without re-querying or re-framing.
Report the ranked drivers with evidence tiers + the path.
