---
description: Size the business opportunity of a finding with a tornado sensitivity analysis.
argument-hint: "<finding to size>"
---

Size the opportunity for: **$ARGUMENTS**

Delegate to the `opportunity-sizer` agent, or use `atlas/lib/sizing.py`. Define the
assumptions as `Assumption(name, base, low, high)` — grounding `base` in
provenance-stamped numbers where possible — pick a `model`, then
`size_opportunity(assumptions, model)`.

Report the base-case impact (with $ and units), the **most_sensitive_to** driver, and
the full tornado range. Always show what the number hinges on; declare any assumption
that isn't a ledger-backed number.
