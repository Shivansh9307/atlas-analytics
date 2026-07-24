---
name: metric-decomposition
description: Contribution analysis and mix-vs-rate maths for decomposing a metric change between two periods. Use whenever a metric moved and you must attribute the move to segments and to mix vs rate — not guess.
---

# Metric decomposition

The implementation is `atlas/lib/decomposition.py` (tested). Use it — do not
recompute by hand.

## Ratio metrics (margin, conversion rate)
`decompose_margin(period1_rows, period2_rows, dim="product_line")` returns an
exact split:

    ΔM = mix + rate + interaction        (this identity is exact)
    mix         = Σ (w2-w1)·m1           # weight/mix shift, rate held at period 1
    rate        = Σ w1·(m2-m1)           # within-segment rate change
    interaction = Σ (w2-w1)(m2-m1)       # residual cross term

where `w_i` = revenue share, `m_i` = segment margin. Read `.dominant_effect()` and
`.as_dict()`. A drop that is `mix`-dominant means the blend got worse, not the unit
economics — a completely different fix from a `rate` drop.

## Additive metrics (revenue, cost)
`additive_contribution(p1, p2, dim, value_key)` → each segment's signed
contribution and its share of the total delta, sorted by magnitude.

## Simpson's paradox
`simpsons_check(p1, p2, dim)` → `paradox=True` when the aggregate moves opposite to
EVERY segment (a mix artefact). Always run it before asserting a cause.

## CLI
`uv run python .claude/skills/metric-decomposition/scripts/decompose.py <source> <region> <p1> <p2>`

## Worked example (the EMEA fixture)
EMEA margin 60%→56% (−4pts). Decomposition: mix −4.0pts, rate ~0, interaction ~0 →
a pure mix shift toward lower-margin Hardware. Rate levers (procurement, pricing)
would not have caught it.
