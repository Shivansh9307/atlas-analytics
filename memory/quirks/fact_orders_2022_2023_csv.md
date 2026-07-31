# Source quirks — fact_orders_2022_2023_csv

Injected into `source-profiler` and `sql-engineer` when this source is in play.
Promote a recurring mistake here into an assertion (mechanical guarantee).

Source: `./data/fact_orders_2022_2023.csv`. 7,942 rows, `order_date`
2022-01-01 → 2023-12-31. Grain: one row per `order_id`.

## Known facts / hazards
- **All money columns are EGP (Egyptian pounds).** `total_revenue`, `total_cost`.
  The table carries NO currency column. Confirmed by the operator 2026-07-31 and
  evidenced in-schema: `dim_products.unit_price_text` carries a literal `EGP`
  prefix on all 345 rows (verified, zero exceptions). Always label the unit on
  output; never present a bare number.
- **This source covers 2022–2023 ONLY. 2024 lives in `fact_orders_2024_csv`**,
  which has an identical schema. A multi-year question spans both.
- **Cross-source queries are NOT possible in one `run()`.** Each
  `CsvDuckDBConnector` holds its own private `:memory:` DuckDB engine
  (`csv_duckdb.py`), so the two order sources cannot be UNIONed or joined in a
  single statement. Query each separately and combine in the report — each number
  then keeps its own query + result hash, so provenance stays intact.
- **`order_status` has three values and ~13% are not Completed:**
  Completed 6,929 / Returned 698 / Cancelled 315. An unfiltered
  `sum(total_revenue)` silently includes cancelled orders that never generated
  cash. See A1.
- `total_revenue` / `total_cost` are per-order totals. Aggregate the sums; do not
  average per-row ratios.
- Foreign keys out to `dim_customers`, `dim_stores`, `dim_employees`, `dim_date`
  (`date_id`) — all separate sources, so the same cross-engine limitation applies
  to any star join.

## Assertions

Promoted from a declared assumption, not yet from a repeated failure.

### A1 — "Revenue" means Completed orders only, unless the user says otherwise.
Declared 2026-07-31 while answering "total revenue by year, 2022 through 2024":

```sql
sum(total_revenue) WHERE order_status = 'Completed'
```

Excludes Cancelled (never generated cash) and Returned (tracked as their own
event in `fact_returns_csv` — netting them here would double-count the deduction).

**This is NOT a resolved `metrics.yaml` entry.** The locked `revenue` metric is
`sum(revenue)` and does not bind to this schema's `total_revenue` column. If a
revenue question recurs on this source, promote a properly locked metric into
`metrics.yaml` rather than re-declaring the definition each run.

Verified baseline under A1 (use to cross-check any re-derivation):
2022 = 13,257,718.50 EGP (3,434 orders) · 2023 = 12,946,983.00 EGP (3,495 orders).
