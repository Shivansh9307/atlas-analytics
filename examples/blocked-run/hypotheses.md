# Exploration — candidate drivers

Target: **non_quality_return** | base rate **5.97%** | rows **12,000**

## Column summaries

| column | kind | distinct | mean | sd | min | max |
|---|---|---|---|---|---|---|
| avg_discount_pct | numeric | 49 | 7.884 | 6.559 | 0.000 | 30.000 |
| total_cost | numeric | 1443 | 2,970.679 | 7,157.968 | 40.000 | 88,410.000 |
| total_quantity | numeric | 16 | 3.609 | 2.444 | 1.000 | 16.000 |
| total_revenue | numeric | 4859 | 3,779.248 | 8,256.402 | 60.000 | 105,577.500 |
| customer_city | categorical | 13 | — | — | — | — |
| customer_gender | categorical | 2 | — | — | — | — |
| customer_loyalty_tier | categorical | 4 | — | — | — | — |
| dominant_subcategory | categorical | 15 | — | — | — | — |
| employee_role | categorical | 5 | — | — | — | — |
| num_distinct_categories | categorical | 2 | — | — | — | — |
| num_line_items | categorical | 5 | — | — | — | — |
| order_year | categorical | 3 | — | — | — | — |
| payment_method | categorical | 6 | — | — | — | — |
| store_name | categorical | 15 | — | — | — | — |

## Threshold scan

| column | shape | cuts | jump | step R² | linear R² |
|---|---|---|---|---|---|
| avg_discount_pct | insufficient | — | 0.000 | 0.000 | 0.000 |
| total_cost | non_monotone | — | 0.011 | 0.465 | 0.000 |
| total_quantity | insufficient | — | 0.000 | 0.000 | 0.000 |
| total_revenue | non_monotone | — | 0.008 | 0.552 | 0.011 |
