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
- `uv run pytest -q` — full test suite.
- `uv run python -c "from atlas.orchestrator import run_analysis; print(run_analysis('...').headline)"`
- Slash commands live in `.claude/commands/` (`/analyze`, `/profile`, `/rca`, …).
- Data Quality Copilot: `/clean <source> [--preview|--apply|--undo|--history]`
  (detect + score + repair to a clean layer), `/catalog [<source>]` (data catalog +
  drift), `/cao "<question>"` (route + cost-estimate a run before executing).

## Extending (plugin architecture)
- A new **repair module**: add a `@register`-decorated `RepairModule` under
  `atlas/quality/modules/` and import it in that package's `__init__` — nothing else
  changes. Behaviour is config-driven via `atlas/quality/rules/*.yaml`.
- A new **copilot** (Governance/PII/…): add a `@register_copilot` `Copilot` in
  `atlas/quality/plugins.py`. No core edits.
