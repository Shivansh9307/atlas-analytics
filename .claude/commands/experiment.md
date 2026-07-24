---
description: Design an A/B test — sample size, power, guardrails, and a pre-registered decision rule.
argument-hint: <baseline_rate> <mde_abs> [primary_metric]
---

Design an experiment for: **$ARGUMENTS**

Delegate to the `experiment-designer` agent, or use `atlas/lib/experiment.py`:
```bash
uv run python -c "
from atlas.lib.experiment import design_experiment
import json; print(json.dumps(design_experiment(<baseline_rate>, <mde_abs>, primary_metric='<metric>').as_dict(), indent=2))"
```

Report per-arm n, total, the **guardrail** metrics, and the plain-English decision
rule. Pre-register sample size + rule before the test (no peeking, one test). If the
required n is impractical, propose a larger MDE or longer run — never an under-powered
test.
