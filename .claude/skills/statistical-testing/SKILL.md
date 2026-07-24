---
name: statistical-testing
description: Which statistical test to use when, plus power, confidence intervals, and seasonality adjustment. Use whenever a finding needs significance or could be noise/seasonal.
---

# Statistical testing

Implementation: `atlas/lib/stats.py` (tested). Report numbers, never a hand-wave.

## Test selector
| Question | Function |
|---|---|
| Two rates/proportions differ? | `two_proportion_ztest(x1,n1,x2,n2)` |
| Two means differ (unequal var)? | `welch_t_test(a, b)` |
| Interval on a proportion? | `proportion_ci(x, n)` (Wilson — robust for small n) |
| Big enough to detect the effect? | `min_detectable_effect(n, base_rate)` |
| Could it be seasonal? | `deseasonalize(series, period)` (STL) |

## Power & honesty
- If the observed effect is below the MDE for the sample, it is **under-powered** —
  flag it and do NOT promote the claim above the `tested` tier.
- `two_proportion_ztest` auto-flags `<10 events per cell`.
- Compare seasonally-comparable periods, or deseasonalize first, before attributing
  a period-over-period move to a cause.

## Tiering
A stat-significant, adequately-powered result earns the `tested` evidence tier.
Significance without power, or correlation only, stays `correlational`.
