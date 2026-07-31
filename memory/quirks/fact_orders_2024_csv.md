# Source quirks — fact_orders_2024_csv

Injected into `source-profiler` and `sql-engineer` when this source is in play.
Promote a recurring mistake here into an assertion (mechanical guarantee).

Source: `./data/fact_orders_2024.csv`. 4,058 rows, `order_date`
2024-01-01 → 2024-12-31. Grain: one row per `order_id`.

Schema is IDENTICAL to `fact_orders_2022_2023_csv` — the two are one logical
orders fact split by year. Read that source's quirk file too; every hazard below
applies to both.

## Known facts / hazards
- **All money columns are EGP (Egyptian pounds).** `total_revenue`, `total_cost`.
  The table carries NO currency column. Confirmed by the operator 2026-07-31 and
  evidenced in-schema: `dim_products.unit_price_text` carries a literal `EGP`
  prefix on all 345 rows (verified, zero exceptions). Always label the unit on
  output; never present a bare number.
- **This source covers 2024 ONLY. 2022–2023 live in `fact_orders_2022_2023_csv`.**
  A multi-year question spans both.
- **Cross-source queries are NOT possible in one `run()`.** Each
  `CsvDuckDBConnector` holds its own private `:memory:` DuckDB engine
  (`csv_duckdb.py`), so the two order sources cannot be UNIONed or joined in a
  single statement. Query each separately and combine in the report — each number
  then keeps its own query + result hash, so provenance stays intact.
- **`order_status` has three values and ~13% are not Completed:**
  Completed 3,513 / Returned 365 / Cancelled 180. An unfiltered
  `sum(total_revenue)` silently includes cancelled orders that never generated
  cash. See A1.
- `total_revenue` / `total_cost` are per-order totals. Aggregate the sums; do not
  average per-row ratios.

## Assertions

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
2024 = 13,448,012.50 EGP (3,513 orders).
