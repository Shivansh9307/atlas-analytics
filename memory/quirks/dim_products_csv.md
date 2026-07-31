# Source quirks — dim_products_csv

Injected into `source-profiler` and `sql-engineer` when this source is in play.
Promote a recurring mistake here into an assertion (mechanical guarantee).

Source: `./data/dim_products.csv`. 345 rows. Grain: one row per `product_id`.

## Known facts / hazards
- **This source is the CURRENCY EVIDENCE for the whole star schema.**
  `unit_price_text` carries a literal `EGP` prefix (e.g. `"EGP 90"`) on all 345
  rows — verified 2026-07-31: prefix distribution is `{EGP: 345}`, zero nulls.
  Every other money column in the schema is unlabeled, so cite this column when
  stating the unit rather than treating EGP as an assumption.
- **`unit_price_text` is redundant with `unit_price`, NOT dirty.** Stripping
  non-numerics from the text and comparing to the numeric column gives **0
  mismatches across all 345 rows**. It is a display-formatted duplicate. Prefer
  the numeric `unit_price` for arithmetic; do not "repair" the text column or
  treat the pair as a data-quality defect. (The Data Quality Copilot scores this
  source 98.0 / Excellent — it agrees.)
- `unit_price` and `unit_cost` are EGP, per-unit. `unit_price >= unit_cost` on
  every row (0 violations), so there is no negative-margin product at list price.
  A negative line margin, if one appears, comes from `discount_pct` in
  `fact_order_details_csv`, not from the product master.
- `product_name_raw` is named `_raw`, implying an uncleaned display string —
  treat as high-cardinality free text, not a segment. Use `category` /
  `subcategory` / `brand` for grouping.
- `is_active` is a flag: confirm whether an analysis should exclude inactive
  products before aggregating the catalogue.
