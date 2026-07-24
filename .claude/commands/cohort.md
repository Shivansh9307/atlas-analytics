---
description: Run cohort retention / vintage / LTV analysis on a source.
argument-hint: <source> [value_column]
---

Run cohort analysis for: **$ARGUMENTS**

Delegate to the `cohort-analyst` agent, or use `atlas/lib/cohort.py` directly. Query
per-user activity rows (via `Connector.run()` so results are provenance-stamped) with
a cohort label and an integer period offset, then:
- `retention_matrix(...)` for the retention curve + `overall_rate(offset)`
- `vintage_compare(matrix, offset)` to rank cohorts
- `cohort_ltv(...)` if a value column is given

Report the retention curve, weakest/strongest vintages, where drop-off concentrates,
and flag any survivorship. No deck unless asked.
