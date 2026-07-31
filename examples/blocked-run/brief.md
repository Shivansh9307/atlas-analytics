# Brief

**Question:** What is driving non-quality return rate across our stores and products, and which products and stores carry the highest risk?

**Decision owner:** VP Retail Operations

**Decision unblocked:** Which order_ids to prioritise for intervention.

**Primary metric:** 'non_quality_return' rate (ratio).

**Comparison window:** cross-sectional (single snapshot; no time dimension required).

**Grain:** one row per order_id.

**Success criteria:** A risk-ranked list with calibrated probabilities, plus odds ratios with confidence intervals for each driver.

**Non-goals:** Causal attribution. A predictive model identifies who is at risk, never why in a causal sense, and never what to do about it.

## Semantic resolution
Resolved metric 'non_quality_return_rate' = count(*) FILTER (WHERE non_quality_return = 1) / count(*)
 (unit=ratio); decomposition=non_decomposable; playbook='logistic'.

## Assumptions (declared, not buried)
- Metric inferred from the question as 'non_quality_return_rate' (locked definition in metrics.yaml).
- Comparison window: Q2 vs Q1, EMEA only.
- Grain: dominant_subcategory. Numbers are full-scan (no sampling on this local source).
