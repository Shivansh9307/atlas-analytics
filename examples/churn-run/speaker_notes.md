# Speaker notes — What is associated with 'Churn': Payment Delay leads a ranked list

## Slide 2: 'Churn' runs at 47.4%; Payment Delay is the strongest signal

The overall Churn rate is 47.4% over 64,374 rows, and that number was independently re-derived by the red team using a different aggregate. The ranked bars are effect sizes, not p-values — on a table this size almost everything is statistically significant, so size is what separates a real driver from noise. These are associations, not proven causes.

## Slide 3: 'Gender' separates the outcome by 8.8 percentage points

Splitting by Gender moves the rate by 8.8 points against a 47.4% base. Each bar carries a Wilson confidence interval in the appendix, and the size-weighted average of these bars reconstructs the overall rate exactly — that identity is what the red team checked.

## Slide 4: 'Payment Delay' is a cliff, not a slope — it steps at [16.0, 21.0]

This is the finding an average or a correlation would hide. Payment Delay is flat and then jumps at [16.0, 21.0]. That changes the intervention: there is a specific point at which risk changes, so the action is a rule at that boundary rather than a gradual push on the whole population.

## Slide 5: Act on the bands, not the averages — and test before believing cause

Three moves. Prioritise the worst segment, because that is where the same effort reaches the most affected population. Treat the threshold columns as bands, because that is how they actually behave. And before spending against any of this as though it were causal, run an experiment — everything on these slides is measured association.
