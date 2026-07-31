# Source quirks — returns_risk_orders

Injected into `source-profiler` and `sql-engineer` when this source is in play.
Promote a recurring mistake here into an assertion (mechanical guarantee).

Source: `MultiCsvJoinConnector` joining 8 files (`fact_orders_2022_2023`,
`fact_orders_2024`, `fact_order_details`, `fact_returns`, `dim_products`,
`dim_stores`, `dim_customers`, `dim_employees`) into one order-grain view —
see `atlas/connectors/sources.yaml` (`returns_risk_orders`, `view_sql`) for the
join. 12,000 rows, one per `order_id`. This exists because every other source
in this schema lives in its own private DuckDB engine (`CsvDuckDBConnector`),
so no `run()` could otherwise query across them.

## Known facts / hazards
- **Never fit a model directly against `returns_risk_orders` — use the
  per-target modeling views.** `returns_risk_orders_quality_model` (target
  `product_quality_return`) and `returns_risk_orders_nonquality_model` (target
  `non_quality_return`) each EXCLUDE the OTHER target flag plus `any_return`,
  `return_reason`, `return_status` — all near-deterministic functions of
  whichever target you're predicting. The generic column-binding layer
  (`binding.py::split_features`) only ever excludes the bound target + entity;
  it has no domain knowledge that these siblings are leakage. Fitting against
  the base view hands the model its own label under another name.
- **Two return-risk targets, not one — do not collapse them.**
  `product_quality_return` (return_reason IN Defective Product, Quality Issue —
  339 orders) and `non_quality_return` (Duplicate Order, Wrong Item Delivered,
  Size Issue, Changed Mind — 717 orders) are different business problems
  (product QA vs. fulfillment/fit) declared as separate targets by operator
  decision 2026-07-31. `any_return` (1,056) is the union of both — use it only
  if the question genuinely doesn't care which kind of return.
- **Counts ALL filed returns regardless of `return_status`.** Refunded (819),
  Pending (150), and Rejected (87) are all counted — a Rejected return still
  reflects a customer-perceived signal. If a question specifically means
  confirmed/completed returns only, filter `return_status = 'Refunded'`
  explicitly rather than assuming this source already does.
- **Product/category attribution is at ORDER grain, approximate for multi-item
  orders.** `fact_returns` identifies which ORDER was returned, not which line
  item. Only 4,843/12,000 orders (`is_single_line_order = 1`) have unambiguous
  product attribution. For the other 7,157, `dominant_category` /
  `dominant_subcategory` / `dominant_brand` / `dominant_product_id` are the
  attributes of that order's highest-**revenue** line item — a reasonable
  proxy, not a fact. Any product-level driver finding should note what fraction
  of its supporting rows are single-line vs. attributed-by-proxy.
- **`dim_customers` had 50 exact-duplicate rows — deduped inline, verified
  safe.** 50 `customer_id` values had one duplicate row each; checked 2026-07-31
  that all 50 are byte-identical duplicates (0 conflicting versions), then
  deduped with `SELECT DISTINCT` in the `customers_dedup` CTE. This is the same
  fix the Data Quality Copilot's `duplicate_detection` module proposes for
  `dim_customers_csv` directly.
- **Do NOT numeric-cast `customer_gender`'s sibling column `phone` if you ever
  clean `dim_customers_csv` directly.** The copilot's auto-plan for that source
  also proposes `TRY_CAST(phone AS DOUBLE)` (`numeric_type_repair`) — wrong,
  these are Egyptian mobile numbers with meaningful leading zeros. Not carried
  into this joined view at all (phone isn't selected here), but flagged so it
  isn't silently applied elsewhere.
- **`store_city`/`store_district`/`store_region` are excluded from the modeling
  views — exact functions of `store_name`.** Verified 2026-07-31: all 15 stores
  map to exactly one city/district/region each. One-hot encoding `store_name`
  (16 levels) alongside any of these three is guaranteed collinear (the
  coarser column's dummies are exact linear combinations of `store_name`'s).
  Same for `dominant_category` (exact function of `dominant_subcategory` — no
  subcategory spans >1 category) and `customer_region` (exact function of
  `customer_city` — no city spans >1 region): both dropped, the finer column
  kept. `dominant_brand` is genuinely independent of subcategory (verified:
  e.g. Samsung spans 5 subcategories) and stays. This was found the hard way —
  the first fit attempt failed with "design matrix is rank-deficient (99 < 148
  columns)" fitting against the un-pruned base view.
- **`store_id`, `is_single_line_order`, `num_distinct_products` are ALSO
  excluded from the modeling views — a second round of the same problem.**
  `store_id` is an exact 1:1 function of `store_name` (verified) and is a
  meaningless numeric label besides — never treat it as a continuous feature.
  `is_single_line_order` is deterministic from `num_line_items == 1` by
  construction. `num_distinct_products` turned out to EXACTLY equal
  `num_line_items` on all 12,000 rows in this dataset (verified — no order
  repeats the same product across multiple lines), so it's a pure duplicate;
  `num_distinct_categories` genuinely differs on 6,508 rows and was kept. This
  took TWO fit attempts to fully resolve (49-dimension deficiency, then an
  18-dimension residual) — if a future column is added to this schema, check
  it against every existing categorical/numeric feature for an exact
  functional relationship before assuming the model will just handle it.
- **Third round: `store_type`, `store_opening_year`, `store_size_sqm` are ALSO
  excluded.** Same principle as store_city/district/region — every store-level
  attribute is an exact per-store constant (verified: 0 stores have >1 value
  for any of these), so ALL of them are redundant given `store_name` is kept
  at full 15-store granularity, not just the geographic ones. If `store_name`
  is ever dropped in favor of coarser store attributes (a legitimate, DIFFERENT
  question — "do larger/older stores carry more risk" rather than "which
  stores") these three become the actual features to use instead.
  `total_revenue`/`total_cost` correlate at r=0.995 but are not exactly linear
  (ratio has real variance) — left in, not a rank-deficiency cause, but read
  their individual coefficients cautiously given the correlation.
- **Fourth round: `dominant_brand` is excluded too — a nested-categorical
  issue, not a redundant-pair issue.** Brand is genuinely NOT redundant with
  subcategory in aggregate (brands span multiple subcategories, e.g. Samsung
  across 5), but SOME brands are confined to exactly one subcategory (Asus
  only in Laptops, Canon only in Printers) — one-hot-encoding a full
  categorical alongside a partially-nested sub-categorical as independent
  blocks is a structural rank deficiency the generic encoder can't avoid.
  Found via `numpy.linalg.matrix_rank` on the actual design matrix (greedy
  column removal), not guessed — the earlier "does a brand span >1
  subcategory" check was necessary but not sufficient to rule this out.
  Kept `dominant_subcategory` (more central to "which products") over brand.
  This closed the LAST rank-deficiency dimension after 4 rounds (49 -> 18 -> 12
  -> 3 -> 0); a future column added to this schema should be checked with the
  same numpy-rank technique, not just pairwise "does X determine Y" checks —
  nested-but-not-fully-determined relationships (like brand/subcategory) don't
  show up in a simple 1:1 functional check.
- **Fifth round, a DIFFERENT failure mode: `order_status` causes quasi-complete
  separation, not rank deficiency.** Verified: BOTH return targets are exactly
  0 for every order not marked `order_status = 'Returned'` (10,442 Completed +
  495 Cancelled orders, zero returns of either kind among them) — a hard
  deterministic rule, since a return record can only exist for a returned
  order. Including `order_status` let the fit trivially perfectly-predict the
  majority class, and `fit_logit` correctly refused with "did not converge"
  rather than reporting divergent coefficients. Same underlying class of
  problem as the leakage columns (a column too entangled with "was this
  order returned at all"), just a different symptom — rank deficiency and
  quasi-separation are BOTH things `atlas/lib/logit.py::fit_logit` checks for
  and refuses on, and a wide joined schema can trip either one independently.
- **`customer_gender` and `payment_method` are canonicalized
  (`upper(trim(...))`) directly in the join**, not left for the Data Quality
  Copilot to repair post-hoc. Reason: the copilot's `case_standardisation`
  module adds a `<col>_Clean` sibling but does NOT cause the raw column to be
  dropped from model feature candidacy — `binding.py::split_features` only
  ever excludes the bound target + entity, so both `payment_method` (6 noisy
  case/whitespace variants) and `payment_method_Clean` (canonical) ended up as
  separate one-hot-encoded features, each a near-duplicate of the other. This
  contributed to the same rank-deficiency failure above. Pre-canonicalizing
  avoids the copilot ever detecting the issue, so no duplicate sibling is ever
  created for these two columns.
- **CSV/TSV only, no Excel, no non-UTF-8 fallback.** `MultiCsvJoinConnector`
  is deliberately narrower than `CsvDuckDBConnector` — none of the 8 files it
  joins need either today. If a future joined source needs them, extend
  `_register_source`, don't route around it.
- Money columns (`total_revenue`, `total_cost`) are EGP, per the same
  in-schema evidence as the other order/return sources — see
  `dim_products_csv.md`.
- **Before adding ANY column to this schema's modeling views, run the check
  rather than the fit.** `uv run python
  .claude/skills/advanced-analytics/scripts/redundancy_check.py --source
  returns_risk_orders --plan runs/<run_id>/feature_plan.json` reproduces every
  exclusion listed above (all five rounds) in ~5s and exits 1 rather than 0. It is
  the promoted artefact for lessons L-0004..L-0007 — see
  `memory/query_templates/pre_model_redundancy.md`. Both current modeling views
  pass it clean; the raw `returns_risk_orders` view does not.
