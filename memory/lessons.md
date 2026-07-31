# Atlas lessons (human-readable index)

One line per lesson: `<id> [tags] <rule>`. The machine source of truth is
`lessons.jsonl`. A lesson that fires twice is promoted to a hard artefact
(locked metric / quirk assertion / hook rule / query assertion) — see the
`memory-protocol` skill. Prompt-injected lessons are best-effort; only promoted
artefacts are guaranteed.

<!-- lessons appended below by retrospective-agent -->
- L-0001 [class:connector-contract,agent:sql-engineer,layer:engine] A Connector subclass backed by a locally writable engine must implement the whole write-side contract — materialize_clean, drop_clean, materialize_scores — before its first run, not just test_connection/get_schema/_execute. Without them the quality node fails on first use and model output can never be measured as SQL, only derived.
- L-0002 [class:copilot-performance,agent:data-quality-copilot,layer:engine] Treat detect_issues()/build_plan() as expensive and O(columns): any quality entry point must thread an already-computed issues list and CleanPlan down to build_plan()/apply() instead of letting them recompute. Node timeouts are sized for narrow single-file sources and a wide joined view is where the redundancy first bites.
- L-0003 [class:feature-leakage,agent:semantic-architect,playbook:logistic] When a source carries several outcome columns derived from one event, give each target its own modeling view that explicitly EXCLUDEs every sibling outcome column (SELECT * EXCLUDE (...) in DuckDB). The generic binder has no domain knowledge of sibling outcomes and will never catch this for you.
- L-0004 [class:collinear-features,agent:sql-engineer,playbook:logistic] Sweep EVERY feature pair for exact functional determinism in one pass before the first fit — for each candidate pair, SELECT finer, count(DISTINCT coarser) FROM t GROUP BY 1 HAVING count(DISTINCT coarser) > 1 must return zero rows — and drop the coarser column of every hierarchy in a single edit. Never discover a schema's hierarchies one failed fit at a time.
- L-0005 [class:duplicate-features,agent:sql-engineer,playbook:logistic] Exclude arbitrary ID numerics from continuous features, exclude any flag that is a CASE over another included column, and test numeric-vs-numeric EXACT equality on the actual data, not on the schema — a duplicate that exists only in this extract still makes the design singular.
- L-0006 [class:rank-verification,agent:sql-engineer,playbook:logistic] A pairwise "does A determine B" check is necessary but never sufficient. Before trusting a fit, encode the design the way the engine does (logit.build_design, drop_first=True) and assert numpy.linalg.matrix_rank(X) == X.shape[1]; when short, greedily drop whole source-column blocks to name the offender rather than guessing.
- L-0007 [class:quasi-separation,agent:root-cause-analyst,playbook:logistic] A status column describing whether the target's linked record could exist at all is leakage-adjacent even when the target is a subtype of that event; exclude it. Recognise both symptoms of the same mistake: rank deficiency AND "did not converge". Confirm with SQL that the target is deterministically constant outside one status value before blaming the optimiser.

## Promotions (2026-07-31, retro of r-20260731-133624)

Only these are guaranteed; the lesson text above is prompt-injected, best-effort.

- **L-0001** → code: `atlas/connectors/multi_csv_join.py` implements
  `materialize_clean` / `drop_clean` / `materialize_scores`. *Mechanical.*
- **L-0002** → code: `issues=` / `plan=` passthrough in
  `atlas/quality/clean_layer.py` + `atlas/quality/pipeline.py`. *Mechanical.*
- **L-0003** (fired 2×) → `atlas/connectors/sources.yaml` per-target modeling views
  that `EXCLUDE` every sibling outcome column, plus the assertion in
  `memory/quirks/returns_risk_orders.md`. *Mechanical for this source; the general
  rule stays best-effort.*
- **L-0004** (fired 3×), **L-0005** (2×), **L-0006**, **L-0007** → one shared query
  template + runnable check: `memory/query_templates/pre_model_redundancy.md` and
  `.claude/skills/advanced-analytics/scripts/redundancy_check.py`. *Deterministic
  when run; not yet invoked automatically by the `model` node.*
