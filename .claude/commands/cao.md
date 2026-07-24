---
description: Chief Analytics Officer — plan a run: route the question, select the cheapest agent path, and estimate cost before executing.
argument-hint: "\"<question>\""
---

Act as the **Chief Analytics Officer**. Before running anything, plan the run for
**$ARGUMENTS**: classify the question, select the cheapest agent path that answers
it (the Data Quality Copilot always runs first — trust before intelligence),
estimate the work, and explain what is skipped.

```
uv run python -c "from atlas.quality.cao import plan_run, render_plan; print(render_plan(plan_run('$ARGUMENTS')))"
```

Report the level, the selected agents, the estimated queries/runtime, what was
skipped (cost-aware) and why, then offer to execute via the recommended command
(`/quick`, `/analyze`, `/forecast`, or `/experiment`). For a simple lookup, do not
spin up the full team; for a genuine root-cause "why", engage all specialists.
