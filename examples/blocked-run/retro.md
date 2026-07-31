# Retrospective — r-20260731-133624

*Forced retrospective (the run halted at GATE 3, so the `retro` node never executed).
Written 2026-07-31 by the memory/retrospective pass.*

**Scope note, up front.** This run executed cleanly in a single pass. The substantive
corrections retrospected here belong to the **analysis session as a whole** — the
sibling target `product_quality_return` against the same `returns_risk_orders` source,
run_ids `r-20260731-121612` → `124455` → `125412` → `125700` → `130149` → `130433` —
not to this run_id's own execution log. This run succeeded first time *because* every
fix from those six attempts was already in `sources.yaml`, `multi_csv_join.py`,
`clean_layer.py` and `pipeline.py` before it started. Reading only this run's artefacts
would produce a retro with nothing in it, which would be a false clean bill of health.

## What this run was
`target=non_quality_return` on the joined view `returns_risk_orders_nonquality_model`
(source `returns_risk_orders`, `MultiCsvJoinConnector`, 12,000 order-grain rows),
metric `non_quality_return_rate`, playbook `logistic`, routing L3 `/analyze`.

## Gates
- GATE1_profiling: PASS
- GATE2_semantics: PASS
- GATE_readiness: PASS
- GATE3_redteam: **FAIL** — held-out AUC 0.4954 vs a 0.60 floor (confidence grade B,
  `L:discrimination FAIL`; every arithmetic re-derivation matched to the last decimal)

**The GATE 3 failure is a correct outcome, not a defect.** A model at chance cannot
honestly rank "highest-risk stores and products", and the pipeline refused to emit a
deck over it (`BLOCKED.md`, no `deck.pptx`, no PBIP). It is recorded here as the
system working, and deliberately **not** written up as a lesson.

## Budget
```json
{
  "queries_used": 23,
  "max_queries": 60,
  "bytes_used": 0,
  "max_bytes_scanned": 5000000000,
  "elapsed_s": 43.5,
  "max_wallclock_s": 1200
}
```

## Detection pass on this run_id
| Mistake class | Found | Evidence |
|---|---|---|
| Validation rejection (GATE 3) | 1, legitimate | `validation.md` — AUC 0.495; all re-derivations in tolerance |
| Query errors / retries | none | `pipeline_state.json` node history is one clean pass: frame → profile → quality → semantics → readiness_gate → explore → model → diagnose → redteam(BLOCKED); no node retried |
| Mid-run human corrections | none in this run | corrections all predate it (see below) |
| Repeated clarifications → new brief default | none evidenced in this run | the one standing operator decision (two separate return metrics, never merged) is *already* a stored default — locked in `atlas/semantic/metrics.yaml` for both metrics and asserted in `memory/quirks/returns_risk_orders.md` |
| Unfingerprinted / orphan numbers | n/a | run halted before GATE 4 |

## Corrections that actually happened (session-level)
| # | run_id where it surfaced | Symptom | Root cause | Fix |
|---|---|---|---|---|
| 1 | `121612` | `connector 'returns_risk_orders' cannot materialise a local clean layer` | new `MultiCsvJoinConnector` implemented the read path only | implement `materialize_clean`/`drop_clean`/`materialize_scores` |
| 2 | `121612` (resumed) | `critical node 'quality' failed: timeout after 180s` | `run_copilot()` recomputed `detect_issues()` 3× and `build_plan()` 2×; ~26s each on a 36-column view | `issues=`/`plan=` passthrough; 157s → 104s |
| 3 | `121612`, `124455` | model handed its own label | sibling outcome columns (`non_quality_return`, `any_return`, `return_reason`, `return_status`) stayed feature candidates | per-target modeling views with `SELECT * EXCLUDE (...)` |
| 4 | `121612`, `124455`, `125412` | `design matrix is rank-deficient (99 < 148)`, then 90<108, then 90<102 | coarse dimension attributes kept alongside the fine column they are an exact function of — **three separate hierarchies, fixed one per failed run** | drop store geography, store attributes, product category |
| 5 | `124455`, `125412` | same, residual | `store_id` a relabelling of `store_name`; `is_single_line_order` a `CASE` over `num_line_items`; `num_distinct_products` == `num_line_items` on all 12,000 rows (an accident of this extract) | drop all three |
| 6 | `125700` | `rank-deficient (90 < 93)` after the pairwise checks came back clean | `dominant_brand` partially nested in `dominant_subcategory` — brands confined to one subcategory make its dummies collinear | drop `dominant_brand`; found by `matrix_rank`, not by inspection |
| 7 | `130149` | `logistic fit did not converge` (a *different* check) | `order_status` — both targets are deterministically 0 for all 10,442 Completed + 495 Cancelled orders, so the majority class was trivially predictable | exclude `order_status` |

Six of the seven cost a whole run each. Items 4-6 are one family of mistake diagnosed
three different ways; item 7 is the same family wearing a different symptom.

## Lessons written
Appended to `memory/lessons.jsonl` (+ index line in `memory/lessons.md`,
fingerprints in `memory/failures.jsonl`) via
`.claude/skills/memory-protocol/scripts/lesson.py add`, which ran its semantic dedup
against the store on every insert. The store was empty before this retro, so dedup was
also run pairwise across the seven drafts: highest Jaccard between any two was **0.144**
(L-0004 vs L-0006), far below the 0.6 duplicate threshold — L-0004 ("sweep for exact
functional determinism up front") and L-0006 ("that sweep is not sufficient; assert
matrix rank") are kept as two lessons because they have different triggers and
different remedies, and collapsing them would have lost the second.

| id | class | fired | promoted |
|---|---|---|---|
| L-0001 | connector-contract | 1 | yes — code |
| L-0002 | copilot-performance | 1 | yes — code |
| L-0003 | feature-leakage | **2** | yes — views + quirk |
| L-0004 | collinear-features | **3** | yes — query template + check |
| L-0005 | duplicate-features | **2** | yes — same |
| L-0006 | rank-verification | 1 | yes — same |
| L-0007 | quasi-separation | 1 | yes — same |

`times_prevented` on L-0003/4/5 records **recurrences observed in this session**, not
prevention events (a `times_prevented_note` field says so in the JSON). That is a
deliberate reading of the promotion rule: a mistake that demonstrably repeated three
times in six hours has earned an artefact as much as one that repeats across three
months, and waiting for it to repeat again after being written down would be theatre.

## Promotions — mechanical vs best-effort
**Mechanical (guaranteed, in code, cannot be forgotten):**
- L-0001 → `atlas/connectors/multi_csv_join.py`: the three write-side methods exist.
  A future run against this connector cannot hit that failure.
- L-0002 → `atlas/quality/clean_layer.py` + `atlas/quality/pipeline.py`: the `issues=` /
  `plan=` passthrough. The redundant recomputation is gone from the code path, not
  discouraged in prose. (Verified 157s → 104s; 380 tests green.)
- L-0003 → `atlas/connectors/sources.yaml`: the two modeling views physically
  `EXCLUDE` every sibling outcome column. As long as a run binds a modeling view, the
  leakage cannot re-enter — for *this source*. The general rule ("give every target its
  own view") remains prompt-injected and best-effort for the next joined source.

**Deterministic when run, but not automatic:**
- L-0004/L-0005/L-0006/L-0007 → `memory/query_templates/pre_model_redundancy.md` and
  `.claude/skills/advanced-analytics/scripts/redundancy_check.py`. The check encodes
  the design through the engine's own `atlas.lib.logit.build_design`, so it cannot
  drift from what the fit will do. Validated against this session's history: it
  re-derives every one of the five rounds of exclusions from the raw view in ~5s
  (exit 1), names `dominant_brand` as the partner behind the last 3 missing
  dimensions, flags `order_status` quasi-separation, and returns exit 0 on both
  surviving modeling views. **But nothing invokes it automatically.** An analyst who
  does not run it still discovers the same problems by burning a run on a failed fit.

**Best-effort only (prompt injection):**
- Every lesson's `rule` text, when injected before a wave. Note a real limitation
  found while writing this: `atlas/lib/context_loader.py::_recent_lessons()` injects
  the **last 8 lessons regardless of tags** — the `source|metric|failure_class`
  fingerprint in `memory/failures.jsonl` is only used by the `lesson.py retrieve` CLI
  path, not by the automatic context bundle. With 7 lessons stored that is currently
  harmless; at 20+ it means the relevant lesson may simply not be in the bundle.

## The honest next mechanical step
The highest-value remaining promotion is to make the redundancy check unconditional:
call it (or its QR diagnosis) from the `model` node / `LogisticPlaybook` so that
`PlaybookBlocked` says *which column* is redundant instead of "check that one-hot
encoding used drop-first". That converts the last four lessons from
deterministic-when-run to mechanical. It is an engine change and was deliberately
left out of this retrospective's scope rather than made silently.

Also left open, deliberately: `atlas/quality/guardrails.py::column_guardrails()` still
re-runs `detect_issues()` on the clean table (a 4th effective detection pass). Advisory
code path, smaller magnitude, wrapped in `try/except` — known, not fixed.

## Artefacts
- This run: `runs/r-20260731-133624/` (`BLOCKED.md`, `validation.md`, `findings.md`,
  `model_card.md`, `feature_plan.json`, `provenance.json`, `risk_scores.csv`)
- Combined user-facing write-up for both targets:
  `runs/returns_risk_summary_2026-07-31.md`
- Source quirks (rounds 1-5, hand-written before this retro):
  `memory/quirks/returns_risk_orders.md`
