# Exploration — candidate drivers

Target: **Churn** | base rate **47.37%** | rows **64,374**

## Column summaries

| column | kind | distinct | mean | sd | min | max |
|---|---|---|---|---|---|---|
| Age | numeric | 48 | 41.971 | 13.925 | 18.000 | 65.000 |
| Last Interaction | numeric | 30 | 15.499 | 8.638 | 1.000 | 30.000 |
| Payment Delay | numeric | 31 | 17.134 | 8.852 | 0.000 | 30.000 |
| Support Calls | numeric | 11 | 5.401 | 3.114 | 0.000 | 10.000 |
| Tenure | numeric | 60 | 31.995 | 17.098 | 1.000 | 60.000 |
| Total Spend | numeric | 901 | 541.023 | 260.875 | 100.000 | 1,000.000 |
| Usage Frequency | numeric | 30 | 15.080 | 8.816 | 1.000 | 30.000 |
| Contract Length | categorical | 3 | — | — | — | — |
| Gender | categorical | 2 | — | — | — | — |
| Subscription Type | categorical | 3 | — | — | — | — |

## Threshold scan

| column | shape | cuts | jump | step R² | linear R² |
|---|---|---|---|---|---|
| Age | non_monotone | — | 0.083 | 0.895 | 0.586 |
| Last Interaction | non_monotone | — | 0.008 | 0.291 | 0.027 |
| Payment Delay | cliff | [16.0, 21.0] | 0.612 | 1.000 | 0.830 |
| Support Calls | cliff | [4.0, 5.0] | 0.354 | 0.999 | 0.769 |
| Tenure | cliff | [6.0, 24.0] | 0.256 | 0.988 | 0.634 |
| Total Spend | non_monotone | — | 0.080 | 0.968 | 0.860 |
| Usage Frequency | cliff | [3.0, 6.0] | 0.239 | 0.987 | 0.441 |
