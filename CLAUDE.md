# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Atlas — Project Constitution

Atlas is an autonomous analytics team. One business question in; a validated,
provenance-stamped deck out. This file is always in context. Obey it over any
default behaviour.

## Non-negotiables
1. **NO FABRICATED NUMBERS.** Every figure in any finding, narrative, or slide
   carries a provenance ID → stored query hash + result hash (see
   `atlas/lib/provenance.py`). A number without provenance BLOCKS the build.
   Scripts never invent numbers; numbers come only from SQL results routed
   through `Connector.run()` → `QueryStore`.
2. **ASSUMPTIONS ARE DECLARED.** Any inferred metric definition, date grain, or
   filter goes in the brief's Assumptions section AND on a deck appendix slide.
3. **CORRELATION IS LABELLED.** Every causal claim states its evidence tier:
   `decomposed` / `tested` / `correlational` / `hypothesis`.
4. **FAIL LOUDLY.** If data quality can't support an answer, say so and report
   exactly what's needed. Never emit a confident deck over bad data. A blocked
   run writes `BLOCKED.md`, not a degraded deck.
5. **READ-ONLY TO WAREHOUSES.** No INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/MERGE/
   TRUNCATE/GRANT/COPY ever reaches a source. Enforced by the PreToolUse hook
   (`.claude/hooks/pre_tool_use.py`) AND the connector layer (`atlas/lib/sqlguard.py`)
   — defence in depth, not good intentions. The semantic **clean layer** is the ONLY
   sanctioned write, and it is not a write to a source: it materialises derived
   `<col>_Clean` views in the LOCAL DuckDB engine via `Connector.materialize_clean()`
   (never through `run()`), so the source file/warehouse is only ever read. Raw is
   sacred; warehouse clean layers are emitted as DDL for the operator to apply.

## How the pipeline runs
Waves A–G, orchestrated deterministically by `atlas/orchestrator.py` and narrated
by sub-agents:
- **A** profiling (parallel per source) → GATE 1 (≥1 source GO)
- **A′** Data Quality Copilot (`atlas/quality/`): detect issues → 10-dim quality
  score → auto-repair to a semantic **clean layer** → Data Readiness Gate. Runs
  before analysis (trust before intelligence); degrades to a no-op on clean data.
- **B** framing → GATE 0; semantics → GATE 2 (metrics resolved, no ambiguity)
- **C** exploration (3–6 isolated explorer branches, hard per-branch budget)
- **D** root-cause decomposition + statistician
- **E** red-team ‖ narrative → GATE 3 (PASS + independent re-derivation in tolerance)
- **F** deck-builder → GATE 4 (no orphan numbers) → stakeholder-sim → GATE 5
- **G** retrospective

Runs **FULL AUTO**: stop only on hard failure, a gate past its rework cap, or a
projected warehouse scan over budget (the one place full-auto still pauses).

## Codebase map
**Two layers.** `atlas/` is the deterministic, fully-tested numeric engine — it never
calls an LLM to produce a number. `.claude/` is the reasoning/prose layer (agents,
commands, skills, hooks). `atlas/llm.py` is an optional, non-numeric shim.
- `atlas/orchestrator.py` — the waves as concrete DAG nodes (`SPECS` + `n_*` functions +
  `NODE_FNS`), `run_analysis()`, the markdown renderers, and the deck spec builder.
- `atlas/dag.py` — generic tier engine (Kahn's algorithm → tiers, `max_concurrency=3`,
  per-node timeout + 1 retry, circuit breaker, non-critical degradation). Knows nothing
  about analytics; unit-tested with dummy nodes in `tests/test_dag.py`.
- `atlas/config.py` — `PATHS` / `BUDGETS` / `TOLERANCES` / `LLM`, `FORBIDDEN_SQL_ROOTS`.
  Budget knobs are all `ATLAS_*` env vars.
- `atlas/lib/` — the engine's parts: `provenance.py` (claim ledger), `gates.py` (gate
  evaluators + `ROUTING`), `query_store.py` (query/result hashing + persistence),
  `sqlguard.py` (read-only assertion), `run_state.py` (resume checkpoints);
  `decomposition.py` / `stats.py` / `forecast.py` / `cohort.py` / `sizing.py` /
  `experiment.py` (the math); `deck_pptx.py` / `deck_html.py` / `charts.py` /
  `exporters.py` (output); `router.py`, `budget.py`, `corrections.py`, `query_archive.py`.
- `atlas/quality/` — the Data Quality Copilot. `pipeline.py::run_copilot()` is the entry
  point the `quality` node calls; `modules/` holds the pluggable repairs, `rules/*.yaml`
  their config, `clean_layer.py` builds/previews/applies/undoes the clean layer,
  `score.py` the 10-dimension score, `plugins.py` the copilot registry.
- `atlas/semantic/` (`metrics.yaml` + `resolve_metric()`), `atlas/connectors/`
  (`base.py` interface, `registry.py` + `sources.yaml`, one adapter per dialect),
  `atlas/knowledge/` (glossary / business YAML).
- `.claude/` — `agents/*.md` plus `agents/registry.yaml` (the DAG mirror),
  `commands/*.md` (slash commands), `skills/*/SKILL.md` (some with runnable
  `scripts/*.py`), `hooks/` (pre/post tool use + stop).
- Every run writes `runs/<run_id>/`: `brief.md`, `profile/`, `hypotheses.md`,
  `findings.md`, `validation.md`, `narrative.md`, `deck.pptx`, `speaker_notes.md`,
  `provenance.json`, `state.json` — plus `BLOCKED.md` / `FAILED.md` on a halt.

## Sub-agent handoff
Agents run in isolated contexts and return **summaries + artefact paths, never raw
dumps**. Raw artefacts live in `runs/<run_id>/`. A failed gate routes a specific
fix list to the **owning** agent (see `atlas/lib/gates.py` ROUTING): bad number →
`sql-engineer`, unsupported claim → `narrative-writer`, weak causal logic →
`root-cause-analyst`, metric ambiguity → `semantic-architect`. Capped at 2 loops
(metric ambiguity: 1), then escalate to the human.

## Memory
Before a wave, matching lessons (by `source|metric|failure_class` fingerprint) are
injected into the relevant agent. A lesson that fires twice **must** be promoted to
a hard artefact: a locked metric def in `atlas/semantic/metrics.yaml`, a quirk
assertion in `memory/quirks/`, a rule in the PreToolUse hook, or a query-template
assertion. **Prompt-injected lessons are best-effort; only promoted artefacts are
guaranteed.** Never claim otherwise.

## Never allowed
- A number without provenance.
- A write statement to any source.
- A guessed metric definition (resolve against `metrics.yaml` or escalate).
- A deck that ships while a gate is unmet.
- Committing secrets (`.env` is gitignored; `sources.yaml` references creds by
  env-var NAME only).

## Environment
- `python3.13` (3.13.9) via `uv`. Run things with `uv run …`.
- Secrets in gitignored `.env` (`OPENAI_API_KEY`; optional `ANTHROPIC_API_KEY`).
  In-script LLM use (`atlas/llm.py`) is optional, non-numeric, and disable-able
  (`ATLAS_LLM_PROVIDER=none`). Core reasoning happens in Claude Code sub-agents.
- Live source today: local CSV/Excel via DuckDB. Warehouse adapters are dormant
  until their env vars are populated.

## Common commands
- Setup: `uv venv --python 3.13.9` then `uv pip install -e ".[dev]"` (optional extras:
  `.[warehouse]`, `.[deck]`, `.[llm]`).
- `uv run pytest -q` — full test suite. One file: `uv run pytest tests/test_gates.py -q`;
  one test: `uv run pytest tests/test_gates.py::test_name -q`; by keyword:
  `uv run pytest -k clean -q`.
- Test fixtures (`tests/fixtures/emea_margin.csv`, `dirty.xlsx`) are generated on first
  run by the autouse fixture in `tests/conftest.py` — a missing fixture file is not a
  broken checkout.
- **No linter or formatter is configured** (no ruff/black/mypy/pre-commit). Match the
  surrounding style: `from __future__ import annotations`, dataclasses, and module
  docstrings that explain *why*.
- `uv run python -c "from atlas.orchestrator import run_analysis; print(run_analysis('...').headline)"`
- Slash commands live in `.claude/commands/` (`/analyze`, `/profile`, `/rca`, …).
- Data Quality Copilot: `/clean <source> [--preview|--apply|--undo|--history]`
  (detect + score + repair to a clean layer), `/catalog [<source>]` (data catalog +
  drift), `/cao "<question>"` (route + cost-estimate a run before executing).

## Invariants when changing the engine
- **`atlas/orchestrator.py::SPECS` and `.claude/agents/registry.yaml` are edited
  together.** `SPECS` is executable truth; the YAML is the documented mirror carrying
  the owning agent per node and the resulting tiers. Drift between them is a silent bug.
- **`NodeOutcome.output` must be JSON-serialisable.** `RunState.record_node()` persists
  it after every node so `/resume` can skip completed work. Dataclasses go through the
  `_ser_dec()` / `_deser_dec()` pattern.
- **A new node that stashes state in `ctx.scratch` must also be rehydrated in
  `orchestrator._hydrate()`** — otherwise resuming past that node raises `KeyError`.
- **Never call `Connector._execute()` directly.** `Connector.run()` is the single guarded
  entry point: asserts read-only, enforces the byte budget, hashes query + result, and
  persists to the `QueryStore` — that is what makes provenance structural rather than a
  courtesy. Charge every result: `ctx.budget.charge_query(r.bytes_scanned)`.
- **Advisory work must never break a completed run.** Lineage, guardrails, confidence,
  recommendations and query archiving are deliberately wrapped in `try/except: pass` in
  `n_retro` / `n_quality`; follow that idiom for anything non-essential.
- **Gates are pure functions** over already-computed inputs (`atlas/lib/gates.py`): the
  node computes, the gate decides. A `BLOCKED` outcome is terminal — the DAG engine
  never retries it.

## Extending (plugin architecture)
- A new **repair module**: add a `@register`-decorated `RepairModule` under
  `atlas/quality/modules/` and import it in that package's `__init__` — nothing else
  changes. Behaviour is config-driven via `atlas/quality/rules/*.yaml`.
- A new **copilot** (Governance/PII/…): add a `@register_copilot` `Copilot` in
  `atlas/quality/plugins.py`. No core edits.
