# Example runs

Two real Atlas runs, committed so the claims in the top-level README can be checked
rather than taken on trust. Both are **unedited output** — the markdown, the JSON
ledger and the `.pptx` are exactly what the pipeline wrote.

> **These are read-only evidence artefacts, not reproducible runs.** `data/` is
> gitignored, so the source CSVs are not in this repository. You can read every
> artefact and verify it is internally consistent; you cannot re-execute these two
> runs without supplying the data yourself.

---

## [`churn-run/`](churn-run/) — a run that passed

`/analyze "what drives churn"` over a **64,374-row** customer dataset (real data, not
the seeded 6,001-row test fixture in `tests/fixtures/`).

| | |
|---|---|
| Headline | Payment Delay is the strongest measured association with churn |
| The finding | At 16 days late, churn steps **10.1% → 71.3%** (7.06×) — a cliff, not a slope |
| Why that matters | 2-cut step R² **1.000** vs linear R² 0.830 — a linear model would understate it |
| Red-team | Re-derived the cliff independently: **0.611904 vs 0.611904** |
| Attacks | none survived |
| Confidence | **Grade A** (1.00); overall 0.94 "Very High" |

Start with [`validation.md`](churn-run/validation.md) (the red-team's independent
re-derivation) and [`provenance.json`](churn-run/provenance.json) (every claim →
`query_hash` → `result_hash` → evidence tier). Then
[`narrative.md`](churn-run/narrative.md) for the written answer and
[`deck.pptx`](churn-run/deck.pptx) for the deliverable.

Note what `narrative.md` refuses to say: *"These are associations measured in a single
snapshot. None of them establishes that changing a driver would change the outcome."*

**A known bug, left visible on purpose.**
[`recommendations.md`](churn-run/recommendations.md) says *"Rebalance the product mix
rather than cut cost"* — margin-playbook advice on a churn analysis, where it makes no
sense. That string is hardcoded at `atlas/orchestrator.py:797` and is emitted for every
run regardless of the question. It is a real defect, it is in the shipped artefact, and
deleting the file from this example would have hidden it. The numeric layer is the part
under test (380 tests); this templated prose is not, and this is what that gap looks
like. Note also `**Estimated impact:** not sized` — the sizing stage genuinely did not
run for this question, and the artefact says so rather than inventing a figure.

Excluded from this copy: `evidence/` and `queries/` (intermediate query dumps, bulky
and not interesting to read).

---

## [`blocked-run/`](blocked-run/) — a run that was refused

`/analyze` on returns risk over **12,000 orders** joined from 9 CSVs. The model fit
cleanly and every arithmetic check passed — and it was still blocked.

| | |
|---|---|
| Held-out AUC | **0.4954** — a coin flip |
| Re-derivations | base rate, confusion matrix, calibration: **all matched exactly** |
| Verdict | **GATE3 red-team veto** — "the model does not earn its complexity" |
| What shipped | **nothing** — no `deck.pptx`, no Power BI project |

This is the more informative of the two runs. It failed on *discrimination*, not on
arithmetic: the pipeline could compute everything correctly and still concluded the
result was not worth presenting. A GATE3 failure halts the DAG before the `deck` and
`emit` nodes ever execute, so no polished artefact exists to be mistaken for a
validated one.

Read [`BLOCKED.md`](blocked-run/BLOCKED.md) (why it stopped and who owns the fix),
[`validation.md`](blocked-run/validation.md) (the re-derivation table plus the
surviving attack), and [`model_card.md`](blocked-run/model_card.md) (the confusion
matrix showing zero predicted positives at every threshold from 0.3 to 0.8).

[`retro.md`](blocked-run/retro.md) is the post-run retrospective: seven lessons written
to `memory/lessons.jsonl`, four of them promoted into a runnable pre-model redundancy
check. It is explicit about which promotions are mechanical and which are best-effort.

Excluded from this copy: `evidence/` (7.7 MB) and `risk_scores.csv` (1.1 MB).
