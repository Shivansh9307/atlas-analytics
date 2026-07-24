---
name: root-cause-playbooks
description: Named diagnostic playbooks — revenue drop, margin compression, churn spike, funnel leak, cost overrun, forecast miss. Use to pick the right decomposition path for a given question shape.
---

# Root-cause playbooks

Guidance. Each playbook names the metric shape, the decomposition, and the traps.
Detailed steps in `reference/`.

## margin compression  (the EMEA example)
Ratio metric. Decompose **mix / rate / interaction** at product/segment grain
(`decompose_margin`). Trap: attributing a mix shift to a rate (cost) problem — the
fix is completely different. Always run `simpsons_check`.

## revenue drop
Additive. `additive_contribution` by segment/product/geo/channel; then split each
big contributor into price × volume. Trap: a few segments usually dominate — rank
by share of delta, don't average.

## churn spike
Rate metric. Cohort by signup period; segment by plan/tenure. Control seasonality.
Trap: survivorship — a cohort present last period but gone this period.

## funnel leak
Stage conversion. Find the stage whose conversion moved most × its volume weight.
Trap: mix of traffic sources changing upstream (a mix effect masquerading as a leak).

## cost overrun
Additive. Contribution by cost category; unit-cost × quantity split. Trap: one-off
vs run-rate — separate them.

## forecast miss
Decompose error into bias (systematic) vs variance; by segment. Trap: blaming the
model when an input assumption changed.

## Every playbook
Assign evidence tiers, rank by explained share, and pass to the red-team for
independent re-derivation before it ships.
