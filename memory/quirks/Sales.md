# Source quirks — Sales

Injected into `source-profiler` and `sql-engineer` when this source is in play.
Promote a recurring mistake here into an assertion (mechanical guarantee).

Source: `./data/Sales.xlsx`, sheet `Sales_Data` (workbook also has a
`Business_Questions` reference sheet — not data). 32,000 rows, 2023-01-01 →
2026-10-18. Grain: one row per `Order_ID` (perfect unique key, 32000 distinct).

## Known facts / hazards
- **`Region` is 34.6% NULL — and it is NOT random.** Every USA (5,376) and Canada
  (5,696) order has `Region = NULL`; the column only ever carries `APAC` or `EMEA`.
  North America simply has no label. NEVER `WHERE Region IS NOT NULL` for a regional
  cut — that silently drops all of North America (~35% of revenue base). Derive
  region from `Country`: USA/Canada → `AMER`. Use `COALESCE` on a Country→Region map.
- **Only the denormalised `Quarter` column is unreliable — `Month` and `Year` are
  fine.** Empirical check (32k rows): `Month` and `Year` reconcile with `Order_Date`
  at 0 mismatches; `Quarter` mismatches on 1,792 rows (5.6%) because it uses a
  **fiscal** quarter scheme, not calendar (e.g. September is labelled `Q4`, not `Q3`).
  The earlier "Month has only 7 distinct values" observation was a red herring — sales
  simply cluster in ~7 months, the labels themselves are correct. For quarterly grain,
  confirm whether the business wants FISCAL (`Quarter`) or CALENDAR quarters before
  deriving `Quarter_Clean` from `Order_Date`; monthly/annual grain can trust the
  stored columns or derive from `Order_Date` interchangeably.
- **`Order_Date` is stored as VARCHAR** (ISO `YYYY-MM-DD`), so the profiler reported
  `freshness = null`. Cast with `CAST(Order_Date AS DATE)` before any date math or
  max-date freshness check. Values parse cleanly.
- `Churn_Reason` is 97.6% NULL by design — populated only for churned customers.
  Expected, not a defect; filter to non-null when analysing churn reasons.
- Money columns (`Revenue`, `COGS`, `Gross_Profit`, `Operating_Cost`,
  `Marketing_Cost`, `Cloud_Cost`, `Payroll_Cost`) are DOUBLE and per-order. Aggregate
  the sums; do not average per-row ratios. `Unit_Price` and `Discount_%` are integers.

## Assertions (none yet)
<!-- e.g. assert count(*) WHERE Region IS NULL == count(*) WHERE Country IN ('USA','Canada') -->
