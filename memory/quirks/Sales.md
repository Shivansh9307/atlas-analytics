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

## Assertions

Promoted from repeated failures. These are mechanical guarantees, not advice.

### A1 — `churn` IS now locked as `customer_churn_rate`. Do not substitute another.
The ambiguity fired twice (`r-20260725-034926`, `r-20260725-041945`) and has since been
resolved: `metrics.yaml` defines `customer_churn_rate`, customer-grain, ANY-order rule:

```
count(distinct case when customer_status='Churned' then customer_id end)
  / count(distinct customer_id)          -- 2026 overall = 12.65%
```

The rejected alternative was **order-grain** (759 / 8,000 = 9.49%). The two differ by
3.2 points — if a question implies order, subscription, or revenue churn, ESCALATE
rather than silently reusing the customer-grain metric.

Grain hazard behind the ambiguity: `Customer_Status` is a **per-order** attribute, not a
per-customer state — all 253 churned customers also hold `Active` orders in 2026. The
locked metric resolves this with the ANY-order rule; any new churn metric must state its
own collapse rule explicitly.

### A2 — Never cut churn by raw `Region`. It silently deletes AMER.
`assert count(*) WHERE Region IS NULL == count(*) WHERE Country IN ('USA','Canada')`

`Region` only ever carries `APAC` or `EMEA`. Every USA/Canada order is `NULL` — 2026
churn by raw `Region`: `NULL` = 270, `APAC` = 258, `EMEA` = 231 (total 759 ✅), where the
NULL bucket is USA (126) + Canada (144) = **AMER**.

Dropping or ignoring nulls removes an entire region covering **692 of 2,000 customers**
(34.6%). Correct 2026 figures on the derived region:

| Region (derived) | `customer_churn_rate` | Churned rows | Customers |
|---|---|---|---|
| APAC | 13.11% | 258 | 656 |
| AMER | 13.01% | 270 | 692 |
| EMEA | 11.81% | 231 | 652 |

⚠️ **Rate and count rank differently.** By churned-row *count* the order is
AMER > APAC > EMEA; by the locked *rate* metric it is APAC > AMER > EMEA. AMER has the
most churned rows but not the highest rate, because it also has the most customers.
State which one a claim uses — they support different headlines.

Use `Sales_clean.Region_Clean` (the Data Quality Copilot's `region_repair` module
derives it from `Country` and auto-applies). Never `Sales.Region`.

### A3 — Churn exists for 2026 only. No period-over-period decomposition is possible.
2023, 2024, 2025 have **zero** rows with `Churn_Reason` / `Customer_Status='Churned'`.
Mix-vs-rate decomposition needs two periods and has one. Churn analysis on this source
is cross-sectional and every resulting claim carries the `correlational` evidence tier —
never `decomposed`. Driver columns available within 2026: `Satisfaction_Score`,
`Support_Tickets`, `Discount_%`, `Subscription_Plan`, `Segment`, `Industry`,
`Sales_Channel`, `Renewal_Status`.
