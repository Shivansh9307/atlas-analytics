---
description: Browse the metric dictionary — locked formulas plus business context and ownership.
argument-hint: "[metric_name]"
---

Browse the metric dictionary: **$ARGUMENTS** (empty = list all).

Merges the LOCKED formulas in `atlas/semantic/metrics.yaml` with business context
(owner team, decision owner, what-to-watch-for) from `atlas/knowledge/business.yaml`:
```bash
uv run python -c "
from atlas.knowledge import metric_dictionary
import json; print(json.dumps(metric_dictionary(), indent=2))"
```

For a specific metric, show: exact expression, unit, aliases, plain-language
definition, owning team + decision owner, decomposition method, and its `watch_for`
note. If a metric the user asks about is NOT in the dictionary, say so and treat it as
ambiguous — resolve it (`atlas.semantic.resolve_metric`) or escalate; never invent a
formula.
