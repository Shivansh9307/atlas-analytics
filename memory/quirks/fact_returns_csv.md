# Source quirks — fact_returns_csv

Injected into `source-profiler` and `sql-engineer` when this source is in play.
Promote a recurring mistake here into an assertion (mechanical guarantee).

Source: `./data/fact_returns.csv`. 1,056 rows. Grain: one row per `return_id`,
keyed to an order via `order_id`.

## Known facts / hazards
- **`return_amount` is EGP (Egyptian pounds).** The table carries NO currency
  column. Confirmed by the operator 2026-07-31 and evidenced in-schema:
  `dim_products.unit_price_text` carries a literal `EGP` prefix on all 345 rows
  (verified, zero exceptions). Always label the unit.
- **Returns are a SEPARATE event, not a deduction already netted into revenue.**
  The standing revenue convention on the orders sources excludes `Returned` orders
  outright (see `fact_orders_*` quirk files, A1). Subtracting `return_amount` from
  a revenue figure computed under that convention DOUBLE-COUNTS the deduction.
  Pick one treatment and state it.
- Row count here (1,056) is close to but NOT identical to the count of
  `order_status = 'Returned'` orders (698 + 365 = 1,063). Reconcile before
  claiming a return rate — the 7-row gap is unexplained and may indicate returns
  against orders in neither orders file, or a status/return-record mismatch.
- `order_id` joins to the `fact_orders_*` sources, which live in separate DuckDB
  engines — that join cannot happen in a single `run()`.
