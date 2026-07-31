# Model card

**Algorithm:** statsmodels Logit (unregularised MLE) | **seed:** 42 | **split:** stratified 25% held out
**Model fingerprint:** `a7a79ab8cd259fd4` | **Scoring fingerprint:** `5bde34291e96c265` | **Tier policy:** `ed0db7d08c126e44`

## Performance (held-out split)

| metric | value |
|---|---|
| ROC-AUC | 0.4954 |
| Precision @ 0.5 | 0.0000 |
| Recall @ 0.5 | 0.0000 |
| F1 | 0.0000 |
| Accuracy | 0.9403 |
| Majority-class accuracy | 0.9403 |
| McFadden pseudo-R² | 0.0127 |

### Confusion matrix

| | predicted 1 | predicted 0 |
|---|---|---|
| **actual 1** | 0 | 179 |
| **actual 0** | 0 | 2821 |

> Accuracy is shown only beside the majority-class baseline. On an imbalanced target, accuracy alone flatters a model that predicts one class for everyone.

## Choosing the cutoff

0.50 is the MODELLING default, not a business decision. The operating cutoff for "who gets flagged and contacted" should be set from the relative cost of missing a churner versus interrupting a loyal customer, which is rarely symmetric. Change it HERE and re-run — never by post-processing the scores, which would put the CSV and the dashboard out of agreement.

| threshold | flagged | precision | recall | F1 |
|---|---|---|---|---|
| 0.3 | 0 | 0.0000 | 0.0000 | 0.0000 |
| 0.4 | 0 | 0.0000 | 0.0000 | 0.0000 |
| 0.5 | 0 | 0.0000 | 0.0000 | 0.0000 |
| 0.6 | 0 | 0.0000 | 0.0000 | 0.0000 |
| 0.7 | 0 | 0.0000 | 0.0000 | 0.0000 |
| 0.8 | 0 | 0.0000 | 0.0000 | 0.0000 |

## Odds ratios (associational)

| feature | OR | 95% CI | p | unit |
|---|---|---|---|---|
| dominant_subcategory=Networking | 2.185 | 0.681–7.016 | 0.189 | vs baseline of 'dominant_subcategory' |
| dominant_subcategory=TVs & Screens | 1.725 | 0.591–5.040 | 0.319 | vs baseline of 'dominant_subcategory' |
| total_revenue | 1.657 | 0.656–4.190 | 0.286 | per 1 SD (8256) of total_revenue |
| total_cost | 0.620 | 0.243–1.585 | 0.318 | per 1 SD (7158) of total_cost |
| dominant_subcategory=Printers | 1.533 | 0.500–4.702 | 0.455 | vs baseline of 'dominant_subcategory' |
| num_line_items=5 | 0.672 | 0.350–1.289 | 0.231 | vs baseline of 'num_line_items' |
| dominant_subcategory=Audio & Wearables | 1.485 | 0.553–3.989 | 0.432 | vs baseline of 'dominant_subcategory' |
| dominant_subcategory=Laptops | 1.407 | 0.469–4.217 | 0.542 | vs baseline of 'dominant_subcategory' |
| store_name=Lotus Tanta Stars | 0.713 | 0.405–1.255 | 0.241 | vs baseline of 'store_name' |
| customer_city=Zagazig | 0.719 | 0.405–1.276 | 0.26 | vs baseline of 'customer_city' |
| dominant_subcategory=Bottoms | 1.363 | 0.580–3.204 | 0.477 | vs baseline of 'dominant_subcategory' |
| num_line_items=3 | 0.744 | 0.510–1.086 | 0.126 | vs baseline of 'num_line_items' |
| store_name=Lotus Sharm Plaza | 1.340 | 0.782–2.295 | 0.287 | vs baseline of 'store_name' |
| customer_city=Aswan | 0.755 | 0.437–1.303 | 0.313 | vs baseline of 'customer_city' |
| dominant_subcategory=Outerwear | 1.300 | 0.555–3.041 | 0.546 | vs baseline of 'dominant_subcategory' |
| dominant_subcategory=Women Wear | 1.295 | 0.555–3.022 | 0.55 | vs baseline of 'dominant_subcategory' |
| employee_role=Department Manager | 0.782 | 0.577–1.061 | 0.114 | vs baseline of 'employee_role' |
| customer_city=Suez | 1.264 | 0.777–2.055 | 0.346 | vs baseline of 'customer_city' |
| num_line_items=4 | 0.794 | 0.492–1.280 | 0.343 | vs baseline of 'num_line_items' |
| payment_method=VODAFONE CASH | 1.254 | 0.928–1.694 | 0.141 | vs baseline of 'payment_method' |
| store_name=Lotus Port Said Mega | 0.800 | 0.474–1.350 | 0.404 | vs baseline of 'store_name' |
| dominant_subcategory=Gaming | 1.242 | 0.381–4.048 | 0.719 | vs baseline of 'dominant_subcategory' |
| customer_city=Mansoura | 1.232 | 0.847–1.792 | 0.275 | vs baseline of 'customer_city' |
| store_name=Lotus Ismailia Festival | 0.815 | 0.458–1.451 | 0.487 | vs baseline of 'store_name' |
| dominant_subcategory=Footwear | 1.197 | 0.509–2.818 | 0.68 | vs baseline of 'dominant_subcategory' |
| store_name=Lotus Hurghada Waterfront | 0.840 | 0.496–1.422 | 0.516 | vs baseline of 'store_name' |
| payment_method=CREDIT CARD | 1.187 | 0.875–1.610 | 0.27 | vs baseline of 'payment_method' |
| customer_loyalty_tier=Silver | 1.174 | 0.962–1.434 | 0.114 | vs baseline of 'customer_loyalty_tier' |
| customer_city=Ismailia | 1.169 | 0.715–1.912 | 0.534 | vs baseline of 'customer_city' |
| payment_method=FAWRY | 1.155 | 0.851–1.568 | 0.356 | vs baseline of 'payment_method' |
| dominant_subcategory=Accessories & Storage | 1.153 | 0.371–3.586 | 0.806 | vs baseline of 'dominant_subcategory' |
| store_name=Lotus Luxor Mall | 0.868 | 0.472–1.598 | 0.65 | vs baseline of 'store_name' |
| customer_city=Luxor | 0.876 | 0.506–1.516 | 0.637 | vs baseline of 'customer_city' |
| dominant_subcategory=Tops | 0.879 | 0.367–2.110 | 0.774 | vs baseline of 'dominant_subcategory' |
| employee_role=Senior Sales Associate | 1.132 | 0.819–1.565 | 0.453 | vs baseline of 'employee_role' |
| employee_role=Store Manager | 1.118 | 0.861–1.451 | 0.402 | vs baseline of 'employee_role' |
| store_name=Lotus Mall of Egypt | 1.108 | 0.769–1.596 | 0.583 | vs baseline of 'store_name' |
| payment_method=INSTAPAY | 1.106 | 0.814–1.504 | 0.519 | vs baseline of 'payment_method' |
| dominant_subcategory=Mobile Phones | 0.911 | 0.315–2.634 | 0.863 | vs baseline of 'dominant_subcategory' |
| store_name=Lotus San Stefano | 1.094 | 0.727–1.645 | 0.667 | vs baseline of 'store_name' |
| store_name=Lotus Suez Canal Mall | 0.916 | 0.559–1.501 | 0.729 | vs baseline of 'store_name' |
| store_name=Lotus Mansoura Mega Mall | 1.090 | 0.715–1.663 | 0.688 | vs baseline of 'store_name' |
| total_quantity | 1.087 | 0.922–1.282 | 0.319 | per 1 SD (2.444) of total_quantity |
| customer_city=Giza | 0.922 | 0.667–1.274 | 0.622 | vs baseline of 'customer_city' |
| customer_city=Hurghada | 1.084 | 0.698–1.684 | 0.719 | vs baseline of 'customer_city' |
| num_distinct_categories=2 | 0.925 | 0.593–1.443 | 0.732 | vs baseline of 'num_distinct_categories' |
| employee_role=Sales Associate | 1.079 | 0.849–1.372 | 0.533 | vs baseline of 'employee_role' |
| customer_city=Port Said | 1.078 | 0.649–1.791 | 0.771 | vs baseline of 'customer_city' |
| avg_discount_pct | 1.071 | 0.980–1.171 | 0.129 | per 1 SD (6.559) of avg_discount_pct |
| store_name=Lotus Zagazig Stars | 1.065 | 0.646–1.758 | 0.804 | vs baseline of 'store_name' |
| store_name=Lotus Cairo Festival City | 1.064 | 0.737–1.535 | 0.741 | vs baseline of 'store_name' |
| store_name=Lotus Aswan Plaza | 1.057 | 0.628–1.780 | 0.834 | vs baseline of 'store_name' |
| order_year=2024 | 0.950 | 0.766–1.180 | 0.645 | vs baseline of 'order_year' |
| customer_city=Tanta | 0.958 | 0.588–1.561 | 0.864 | vs baseline of 'customer_city' |
| payment_method=DEBIT CARD | 0.959 | 0.697–1.319 | 0.796 | vs baseline of 'payment_method' |
| customer_loyalty_tier=Platinum | 1.038 | 0.666–1.616 | 0.869 | vs baseline of 'customer_loyalty_tier' |
| num_line_items=2 | 1.037 | 0.809–1.329 | 0.776 | vs baseline of 'num_line_items' |
| customer_city=Sharm El Sheikh | 0.970 | 0.378–2.490 | 0.95 | vs baseline of 'customer_city' |
| store_name=Lotus City Stars | 0.975 | 0.664–1.430 | 0.896 | vs baseline of 'store_name' |
| customer_gender=MALE | 1.025 | 0.859–1.223 | 0.788 | vs baseline of 'customer_gender' |
| customer_loyalty_tier=Gold | 1.024 | 0.786–1.333 | 0.862 | vs baseline of 'customer_loyalty_tier' |
| customer_city=Cairo | 0.983 | 0.732–1.319 | 0.908 | vs baseline of 'customer_city' |
| order_year=2023 | 0.987 | 0.797–1.223 | 0.906 | vs baseline of 'order_year' |
| dominant_subcategory=Tablets | 0.992 | 0.302–3.265 | 0.99 | vs baseline of 'dominant_subcategory' |

## Plain language

- Customers vs baseline of 'dominant_subcategory' show **2.19x higher odds** of the outcome (95% CI 0.68-7.02, p=0.189). This is an association measured in this dataset, not a demonstrated cause.
- Customers vs baseline of 'dominant_subcategory' show **1.73x higher odds** of the outcome (95% CI 0.59-5.04, p=0.319). This is an association measured in this dataset, not a demonstrated cause.
- Customers per 1 SD (8256) of total_revenue show **1.66x higher odds** of the outcome (95% CI 0.66-4.19, p=0.286). This is an association measured in this dataset, not a demonstrated cause.
- Customers per 1 SD (7158) of total_cost show **1.61x lower odds** of the outcome (95% CI 0.24-1.59, p=0.318). This is an association measured in this dataset, not a demonstrated cause.
- Customers vs baseline of 'dominant_subcategory' show **1.53x higher odds** of the outcome (95% CI 0.50-4.70, p=0.455). This is an association measured in this dataset, not a demonstrated cause.

## Preprocessing

- Binned (measured non-linear, one-hot not ordinal): none
- Numerics standardised; coefficients are per 1 SD
- Excluded: ['customer_id', 'dominant_product_id', 'non_quality_return', 'order_date', 'order_id']

## Limitations

- Observational fit: coefficients are associations, never causes.
- Trained and evaluated on one snapshot; no temporal validation.
- Flags: none
