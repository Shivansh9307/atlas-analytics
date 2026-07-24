# Source quirks — emea_finance_csv

Injected into `source-profiler` and `sql-engineer` when this source is in play.
Promote a recurring mistake here into an assertion (mechanical guarantee).

## Known facts
- Grain: one row per (region, quarter, product_line, segment). No natural surrogate
  key; the full column tuple is the grain. Confirm uniqueness before aggregating.
- `revenue` and `cogs` are in the same currency, already period-scoped. Margin =
  (revenue - cogs) / revenue. Do NOT average per-row margins — aggregate the sums.
- Quarters are labels `Q1..Q4`, not dates. Ordering is lexical-correct here.

## Assertions (none yet)
<!-- e.g. assert sum(revenue) > 0 per (region, quarter) before computing margin -->
