# Findings — ranked associations

**Overall 'non_quality_return' rate:** 5.97% across 12,000 rows [c_base_rate].

> Ranking uses a heuristic score that maps different effect measures onto one scale so they can be listed together. It is an ordering aid, **not a statistical statement**; read the effect size and interval.

| # | column | finding | effect | p | tier |
|---|---|---|---|---|---|
| 1 | employee_role | 'employee_role' splits the outcome: 'None' runs 3.6% vs 6.0% overall (-2.3pp, n=632) | -2.3358 (rate_gap_pp) | 0.0109 | tested |
| 2 | dominant_subcategory | 'dominant_subcategory' splits the outcome: 'Networking' runs 9.6% vs 6.0% overall (+3.6pp, n=94) | +3.5995 (rate_gap_pp) | 0.1394 | correlational |
| 3 | store_name | 'store_name' splits the outcome: 'Lotus Tanta Stars' runs 4.1% vs 6.0% overall (-1.8pp, n=555) | -1.8309 (rate_gap_pp) | 0.0624 | correlational |
| 4 | avg_discount_pct | 'avg_discount_pct' is associated with the outcome (r=+0.016): higher values occur more often among positives | +0.0156 (pearson_r) | 0.0865 | correlational |
| 5 | customer_city | 'customer_city' splits the outcome: 'Aswan' runs 4.5% vs 6.0% overall (-1.4pp, n=463) | -1.4394 (rate_gap_pp) | 0.1826 | correlational |
| 6 | customer_loyalty_tier | 'customer_loyalty_tier' splits the outcome: 'Silver' runs 6.6% vs 6.0% overall (+0.6pp, n=3,502) | +0.6498 (rate_gap_pp) | 0.0539 | correlational |
| 7 | payment_method | 'payment_method' splits the outcome: 'CASH' runs 5.4% vs 6.0% overall (-0.6pp, n=2,070) | -0.6127 (rate_gap_pp) | 0.1961 | correlational |
| 8 | total_revenue | 'total_revenue' is associated with the outcome (r=+0.006): higher values occur more often among positives | +0.0056 (pearson_r) | 0.5379 | correlational |
| 9 | total_quantity | 'total_quantity' is associated with the outcome (r=+0.005): higher values occur more often among positives | +0.0052 (pearson_r) | 0.5701 | correlational |
| 10 | total_cost | 'total_cost' is associated with the outcome (r=+0.005): higher values occur more often among positives | +0.0052 (pearson_r) | 0.5706 | correlational |
| 11 | num_line_items | 'num_line_items' splits the outcome: '4' runs 5.5% vs 6.0% overall (-0.5pp, n=1,153) | -0.5110 (rate_gap_pp) | 0.4413 | correlational |
| 12 | order_year | 'order_year' splits the outcome: '2022' runs 6.2% vs 6.0% overall (+0.2pp, n=3,955) | +0.1944 (rate_gap_pp) | 0.5287 | correlational |
| 13 | customer_gender | 'customer_gender' splits the outcome: 'FEMALE' runs 6.1% vs 6.0% overall (+0.1pp, n=5,394) | +0.0873 (rate_gap_pp) | 0.7154 | correlational |
| 14 | num_distinct_categories | 'num_distinct_categories' splits the outcome: '2' runs 6.0% vs 6.0% overall (+0.0pp, n=1,888) | +0.0102 (rate_gap_pp) | 0.9838 | correlational |

## Threshold effects (must be binned before linear modelling)

- none detected

## Evidence tier

All findings here are **correlational** unless marked `tested` (a significance test backs the specific comparison). Nothing in this document establishes causation.
