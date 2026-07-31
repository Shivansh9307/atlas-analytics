# Narrative — for VP Customer Success

## Answer (one sentence)
The strongest measured association with 'Churn' is **Payment Delay**; overall rate is 47.4% [c_base_rate].

## Why (ranked associations)
1. **Payment Delay** — 'Payment Delay' has a threshold effect at [16.0, 21.0]: the rate steps by 61.2% across the cut, not gradually [c_f_thresh_payment_delay]
2. **Support Calls** — 'Support Calls' has a threshold effect at [4.0, 5.0]: the rate steps by 35.4% across the cut, not gradually [c_f_thresh_support_calls]
3. **Tenure** — 'Tenure' has a threshold effect at [6.0, 24.0]: the rate steps by 25.6% across the cut, not gradually [c_f_thresh_tenure]

## Threshold effects
- **Payment Delay**: steps at [16.0, 21.0] — a linear model would understate this (strongest step up at 16: rate 0.1010 -> 0.7129 (jump 0.6119, ratio 7.06); 2-cut step R2 1.000 vs linear R2 0.830 -> removes 100% of the line's residual error)
- **Support Calls**: steps at [4.0, 5.0] — a linear model would understate this (strongest step up at 5: rate 0.2546 -> 0.6090 (jump 0.3545, ratio 2.39); 2-cut step R2 0.999 vs linear R2 0.769 -> removes 100% of the line's residual error)
- **Tenure**: steps at [6.0, 24.0] — a linear model would understate this (strongest step up at 24: rate 0.3028 -> 0.5592 (jump 0.2565, ratio 1.85); 2-cut step R2 0.988 vs linear R2 0.634 -> removes 97% of the line's residual error)
- **Usage Frequency**: steps at [3.0, 6.0] — a linear model would understate this (strongest step down at 3: rate 0.6932 -> 0.4542 (jump 0.2390, ratio 1.53); 2-cut step R2 0.987 vs linear R2 0.441 -> removes 98% of the line's residual error)

## So what
Target the segments above, and treat the threshold columns as bands rather than linear dials.

## What this does NOT say
These are associations measured in a single snapshot. None of them establishes that changing a driver would change the outcome; that requires an experiment (see `/experiment`).
