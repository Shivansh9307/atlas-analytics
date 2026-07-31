# Source quirks — fact_order_details_csv

Injected into `source-profiler` and `sql-engineer` when this source is in play.
Promote a recurring mistake here into an assertion (mechanical guarantee).

Source: `./data/fact_order_details.csv`. 25,099 rows. Grain: one row per
`detail_id` — the ORDER LINE, not the order. Multiple lines per `order_id`.

## Known facts / hazards
- **All money columns are EGP (Egyptian pounds):** `unit_price`, `selling_price`,
  `unit_cost`, `line_total_revenue`, `line_total_cost`. The table carries NO
  currency column. Confirmed by the operator 2026-07-31 and evidenced in-schema:
  `dim_products.unit_price_text` carries a literal `EGP` prefix on all 345 rows
  (verified, zero exceptions). Always label the unit.
- **Line grain vs order grain — do not mix.** `sum(line_total_revenue)` here and
  `sum(total_revenue)` in the `fact_orders_*` sources answer different questions.
  Reconcile the two before using them in the same claim; do not assume they match.
- **`order_status` does NOT exist on this table.** It lives on the orders sources.
  The Completed-only revenue convention (see the `fact_orders_*` quirk files, A1)
  therefore CANNOT be applied here without a join — and that join crosses a source
  boundary, so it cannot happen in one `run()` (each `CsvDuckDBConnector` has its
  own private `:memory:` DuckDB engine). A line-level revenue figure filtered by
  order status needs the status list pulled separately and applied in a second step.
- `discount_pct` is a percentage, not a ratio — confirm the scale before arithmetic.
