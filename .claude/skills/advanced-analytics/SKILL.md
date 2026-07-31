---
name: advanced-analytics
description: Cohort/retention, forecasting, opportunity sizing, experiment design, SQL result sanity checks, and the 4-layer confidence-graded validator. Use to go beyond decomposition into retention, time-series, impact sizing, A/B design, or query correctness.
---

# Advanced analytics

All deterministic `atlas/lib/` modules with known-answer tests. Numbers still come
only from provenance-stamped queries; these modules shape them, never invent them.

## Cohort (`cohort.py`)
`retention_matrix(rows, user_key=, cohort_key=, offset_key=)` → rates + `overall_rate`.
`cohort_ltv(...)` cumulative value/user. `vintage_compare(matrix, offset)`. Watch
survivorship. → `cohort-analyst`, `/cohort`.

## Forecast (`forecast.py`)
`fit_trend` (slope/direction/r²), `detect_anomalies` (robust MAD), `seasonality_strength`
(STL), `forecast(series, horizon, period=)` → points + band + method. Never a bare
point. → `forecaster`, `/forecast`.

## Sizing (`sizing.py`)
`Assumption(name, base, low, high)` + a `model` → `size_opportunity` returns base case
+ a **tornado** (`most_sensitive_to`). A point estimate without a tornado is a guess
with a decimal point. → `opportunity-sizer`, `/size`.

## Experiment (`experiment.py`)
`sample_size`, `power_at`, `design_experiment` → n/arm, **guardrails**, decision rule.
Pair every success metric with a guardrail; pre-register; no peeking. → `experiment-designer`, `/experiment`.

## SQL sanity (`sql_sanity.py`)
`check_percentages_sum`, `check_no_duplicate_keys`, `check_date_bounds`,
`check_join_cardinality` (fan-out), `check_temporal_coverage`. Correctness guards that
complement provenance — run them on result rows in the `sql-engineer` path.

## Validation + confidence (`validation.py`)
4 layers — structural / logical (decomposition identity) / business (plausible ranges)
/ Simpson — graded **A–F** (`validate_margin_finding`). Advisory: it annotates the
red-team's verdict and a grade **F** adds a surviving attack, but it never overrides
the Gate 3 veto. See [[validation-protocol]].

## Pre-model redundancy check (`scripts/redundancy_check.py`)
Run BEFORE the first fit of any interpretable model on a joined/star-schema source:
`uv run python .claude/skills/advanced-analytics/scripts/redundancy_check.py --source <s>
--target <col>` (or `--plan runs/<id>/feature_plan.json`). Four checks — functional
determinism between encoded columns, exact duplicates, design-matrix rank via
`atlas.lib.logit.build_design` + QR (which NAMES the dependent dummies), and a
quasi-separation screen. Exit 1 = do not fit yet. Promotion artefact for lessons
L-0004/L-0005/L-0006/L-0007; rationale in `memory/query_templates/pre_model_redundancy.md`.
