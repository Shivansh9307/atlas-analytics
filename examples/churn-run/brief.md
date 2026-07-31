# Brief

**Question:** what drives churn

**Decision owner:** VP Customer Success

**Decision unblocked:** Where to intervene on 'Churn'.

**Primary metric:** 'Churn' rate (ratio).

**Comparison window:** cross-sectional (single snapshot; no time dimension required).

**Grain:** one row per CustomerID.

**Success criteria:** A ranked list of measured associations, each with an effect size, a confidence interval and a provenance ID.

**Non-goals:** Causal attribution; forecasting. Associations measured here do not establish that changing a driver changes the outcome.

## Semantic resolution
Resolved metric 'customer_churn_rate' = count(distinct case
  when customer_status = 'Churned'
  then customer_id
end) / count(distinct customer_id)
 (unit=ratio); decomposition=non_decomposable; playbook='descriptive'.

## Assumptions (declared, not buried)
- Metric inferred from the question as 'customer_churn_rate' (locked definition in metrics.yaml).
- Comparison window: Q2 vs Q1, EMEA only.
- Grain: product_line. Numbers are full-scan (no sampling on this local source).
- Role 'target' inferred as 'Churn' by name hint — not explicitly specified. Pin it with bind={'target': '<column>'} to be certain.
- Role 'entity' inferred as 'CustomerID' by name hint — not explicitly specified. Pin it with bind={'entity': '<column>'} to be certain.
