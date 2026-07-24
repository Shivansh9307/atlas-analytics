---
description: Log a data or methodology correction so Atlas doesn't repeat the mistake.
argument-hint: "<what was wrong> -> <the correct answer>"
---

Log a correction: **$ARGUMENTS**

A correction is you telling Atlas it got something wrong (wrong column, wrong metric
meaning, wrong filter). It's a stronger signal than a passive lesson.

```bash
uv run python -c "
from atlas.lib.corrections import log_correction
c = log_correction('<what was wrong>', '<correct answer>', wrong='<what Atlas had>', cls='<class>', scope='<metric:x|source:y>')
print(c.id, '| promotion:', c.promotion_hint)"
```

Pick the `cls`: `metric-definition`, `source-quirk`, `unsafe-write`, `filter-leakage`
(these are **promotable** to a mechanical guarantee) or `analytical` (stays a
best-effort lesson). If the class is promotable, follow the printed promotion hint
now — e.g. lock the metric in `atlas/semantic/metrics.yaml` — so the fix is
structural, not just remembered. Then record whether the knowledge system should have
caught it with `corrections.log_miss(...)`.
