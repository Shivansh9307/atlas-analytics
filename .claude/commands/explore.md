---
description: Re-run only the exploration wave against a run's stored brief and metrics.
argument-hint: <run_id>
---

Re-run exploration (Wave C) for run **$ARGUMENTS**.

Read the stored `brief.md` and locked metrics. Spawn 3–6 `explorer` agents in
parallel (time / segment / cohort / mix / funnel / external), each isolated with a
hard per-branch budget. Update `hypotheses.md` and the `evidence/` store.

Use this to redo exploration after feedback without paying for the whole pipeline.
Report each branch's evidence-for / evidence-against / confidence.
