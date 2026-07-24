---
description: Root-cause analysis only — decompose a metric change over a window, skipping the framing wave.
argument-hint: <metric> <window>
---

Run root-cause decomposition only for: **$ARGUMENTS**

Skip framing. Resolve the metric against `atlas/semantic/metrics.yaml`
(`semantic-architect`), then run `root-cause-analyst` + `statistician`:
- ratio metric → `decompose_margin` (mix / rate / interaction, exact identity)
- additive metric → `additive_contribution`
- always run `simpsons_check`

Label each candidate cause with its evidence tier (decomposed / tested /
correlational / hypothesis). Rank by share of the delta. Write `findings.md` under
a fresh `runs/<run_id>/`. Report the ranked drivers + the path. No deck.
