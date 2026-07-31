# Findings — ranked associations

**Overall 'Churn' rate:** 47.37% across 64,374 rows [c_base_rate].

> Ranking uses a heuristic score that maps different effect measures onto one scale so they can be listed together. It is an ordering aid, **not a statistical statement**; read the effect size and interval.

| # | column | finding | effect | p | tier |
|---|---|---|---|---|---|
| 1 | Payment Delay | 'Payment Delay' has a threshold effect at [16.0, 21.0]: the rate steps by 61.2% across the cut, not gradually | +0.6119 (cliff_jump) | 0.00e+00 | tested |
| 2 | Payment Delay | 'Payment Delay' is associated with the outcome (r=+0.557): higher values occur more often among positives | +0.5574 (pearson_r) | 0.00e+00 | tested |
| 3 | Support Calls | 'Support Calls' has a threshold effect at [4.0, 5.0]: the rate steps by 35.4% across the cut, not gradually | +0.3545 (cliff_jump) | 0.00e+00 | tested |
| 4 | Support Calls | 'Support Calls' is associated with the outcome (r=+0.305): higher values occur more often among positives | +0.3046 (pearson_r) | 0.00e+00 | tested |
| 5 | Tenure | 'Tenure' has a threshold effect at [6.0, 24.0]: the rate steps by 25.6% across the cut, not gradually | +0.2565 (cliff_jump) | 0.00e+00 | tested |
| 6 | Usage Frequency | 'Usage Frequency' has a threshold effect at [3.0, 6.0]: the rate steps by 23.9% across the cut, not gradually | +0.2390 (cliff_jump) | 0.00e+00 | tested |
| 7 | Tenure | 'Tenure' is associated with the outcome (r=+0.195): higher values occur more often among positives | +0.1953 (pearson_r) | 0.00e+00 | tested |
| 8 | Usage Frequency | 'Usage Frequency' is associated with the outcome (r=-0.115): lower values occur more often among positives | -0.1151 (pearson_r) | 1.05e-188 | tested |
| 9 | Gender | 'Gender' splits the outcome: 'Male' runs 38.6% vs 47.4% overall (-8.8pp, n=30,021) | -8.7888 (rate_gap_pp) | 0.00e+00 | tested |
| 10 | Total Spend | 'Total Spend' is associated with the outcome (r=-0.079): lower values occur more often among positives | -0.0789 (pearson_r) | 2.41e-89 | tested |
| 11 | Age | 'Age' is associated with the outcome (r=+0.063): higher values occur more often among positives | +0.0635 (pearson_r) | 1.96e-58 | tested |
| 12 | Contract Length | 'Contract Length' splits the outcome: 'Monthly' runs 51.6% vs 47.4% overall (+4.2pp, n=22,130) | +4.2402 (rate_gap_pp) | 0.00e+00 | tested |
| 13 | Subscription Type | 'Subscription Type' splits the outcome: 'Basic' runs 48.3% vs 47.4% overall (+0.9pp, n=21,451) | +0.9090 (rate_gap_pp) | 0.0011 | tested |
| 14 | Last Interaction | 'Last Interaction' is associated with the outcome (r=-0.003): lower values occur more often among positives | -0.0028 (pearson_r) | 0.4746 | correlational |

## Threshold effects (must be binned before linear modelling)

- **Payment Delay** — strongest step up at 16: rate 0.1010 -> 0.7129 (jump 0.6119, ratio 7.06); 2-cut step R2 1.000 vs linear R2 0.830 -> removes 100% of the line's residual error
- **Support Calls** — strongest step up at 5: rate 0.2546 -> 0.6090 (jump 0.3545, ratio 2.39); 2-cut step R2 0.999 vs linear R2 0.769 -> removes 100% of the line's residual error
- **Tenure** — strongest step up at 24: rate 0.3028 -> 0.5592 (jump 0.2565, ratio 1.85); 2-cut step R2 0.988 vs linear R2 0.634 -> removes 97% of the line's residual error
- **Usage Frequency** — strongest step down at 3: rate 0.6932 -> 0.4542 (jump 0.2390, ratio 1.53); 2-cut step R2 0.987 vs linear R2 0.441 -> removes 98% of the line's residual error

## Evidence tier

All findings here are **correlational** unless marked `tested` (a significance test backs the specific comparison). Nothing in this document establishes causation.
