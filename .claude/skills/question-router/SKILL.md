---
name: question-router
description: Classify any business question L1–L5 and route it to the cheapest path that answers it, so a lookup costs a lookup and only genuine root-cause questions trigger the full pipeline. Use at the start of every request.
---

# Question router

Before running anything, classify the ask (`atlas/lib/router.py::classify`):

| Level | Shape | Route |
|---|---|---|
| L1 lookup | "what's X", "how many" | `/quick` |
| L2 breakdown | "X by Y", "compare", "top N" | `/quick` |
| L3 root-cause | "why did X…", "what's driving" | `/analyze` (full pipeline) |
| L4 forecast | "forecast", "will we hit", "next quarter" | `/forecast` |
| L5 experiment | "A/B test", "should we test", "sample size" | `/experiment` |

Rules:
- **Most-specific wins**: experiment > forecast > root-cause > breakdown > lookup. A
  "why … by segment" is root-cause, not a breakdown.
- A simple lookup should not spin up 18 agents. Only L3 earns the full pipeline.
- If confidence is **low**, ask ONE clarifying question before committing.
- Plain English works — the user never has to know the command; you pick it.

`/route "<question>"` shows the classification explicitly.
