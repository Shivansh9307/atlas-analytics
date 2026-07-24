# Atlas — an autonomous analytics team inside Claude Code

Ask one business question in plain English. Atlas frames it, connects to your data,
finds the root cause by **decomposition (not vibes)**, red-teams the result, writes an
executive narrative, and ships a `.pptx` with speaker notes — where **every number
traces back to a query you can re-run.**

```
/analyze "Why did EMEA gross margin drop 4pts in Q2?"
```
```
COMPLETE | EMEA gross margin fell 4.0pts (60.0% → 56.0%), driven by mix.
GATE1=PASS GATE2=PASS GATE3=PASS GATE4=PASS GATE5=PASS
→ runs/r-YYYYMMDD-HHMMSS/deck.pptx  (8 slides, provenance-stamped)
```

---

## Mental model (read this first)

Atlas is two layers that never blur:

| Layer | Lives in | Owns | Why it matters |
|---|---|---|---|
| **Deterministic backbone** | `atlas/` | The numbers, the gates, provenance, budgets | Testable without any LLM. A number here always came from a stored SQL result. |
| **Agent layer** | `.claude/agents/` | Reasoning, judgement, prose | 12 specialists in isolated contexts. They *narrate and decide*; they don't invent numbers. |

### Enterprise capabilities

Beyond the core decomposition pipeline, Atlas ships:

- **Resilient DAG engine** (`atlas/dag.py`) — parallel tiers, per-node timeout + retry,
  circuit breaker, graceful degradation; runs are **tracked and resumable**
  (`/runs`, `/resume`) with no re-query of completed work.
- **Knowledge moat** — business glossary + metric dictionary (`/business`, `/metrics`),
  **query archaeology** (reuse proven SQL), a session context loader, and explicit
  **corrections** with promotion-to-code (`/log-correction`).
- **Analytical depth** — cohort/retention, forecasting, opportunity sizing (+tornado),
  A/B design, SQL sanity checks, and a **4-layer A–F confidence grade**.
- **Deliverable craft** — Storytelling-with-Data charts, a self-contained **HTML** deck,
  **Slack/email/exec** comms, guardrails + close-the-loop — every format behind the
  same provenance gate.
- **Routing & onboarding** — an L1–L5 **question router** (a lookup costs a lookup),
  `/setup`, and a connection **fallback chain** that always reports the active source.

Five non-negotiables (full text in `CLAUDE.md`):

1. **No fabricated numbers** — every figure carries a provenance ID → query hash + result hash.
2. **Assumptions are declared** — never buried; they appear in the brief and a deck appendix.
3. **Correlation is labelled** — every causal claim states its tier: `decomposed / tested / correlational / hypothesis`.
4. **Fail loudly** — bad data ⇒ a `BLOCKED.md` saying what's needed, never a confident deck.
5. **Read-only to sources** — writes are blocked at the connector *and* the pre-tool hook.

---

## 1. Setup

Requires macOS/Linux, Python **3.13**, and [`uv`](https://github.com/astral-sh/uv).

```bash
uv venv --python 3.13.9
uv pip install -e ".[dev]"          # core + pytest. Everything below runs on this.

# optional extras, only when you need them:
uv pip install -e ".[warehouse]"    # Postgres / Snowflake / BigQuery / Databricks drivers
uv pip install -e ".[deck]"         # Google Slides export
uv pip install -e ".[llm]"          # optional in-script LLM judge (OpenAI)

cp .env.example .env                 # fill in ONLY what you use; .env is gitignored
```

The core pipeline (local CSV/Excel → deck) needs **no API key and no credentials**.
`.env` only matters once you enable a warehouse or the optional LLM judge.

Sanity check:

```bash
uv run pytest -q                     # 47 tests, all green
```

---

## 2. Run the full pipeline

### The command
```
/analyze "Why did EMEA gross margin drop 4pts in Q2?"
```
Runs **full-auto** through seven waves, stopping only on a hard failure, a gate past
its rework cap, or a projected warehouse scan over budget:

| Wave | Who | Gate |
|---|---|---|
| **A** Profile every source (parallel) | `source-profiler` | **G1**: ≥1 source `GO` |
| **B** Frame the brief → lock metrics | `requirements-analyst` → `semantic-architect` | **G2**: zero metric ambiguity |
| **C** Explore 3–6 hypotheses (parallel, isolated) | `explorer` ×N | — |
| **D** Decompose + test | `root-cause-analyst` → `statistician` | — |
| **E** Red-team ‖ draft narrative | `red-team-validator` ‖ `narrative-writer` | **G3**: PASS + re-derivation within ±0.5% |
| **F** Build deck → simulate exec Q&A | `deck-builder` → `stakeholder-simulator` | **G4**: no orphan numbers · **G5**: hard Qs answerable |
| **G** Retrospective | `retrospective-agent` | — |

A failed gate routes a **specific fix list to the owning agent** (bad number →
`sql-engineer`, unsupported claim → `narrative-writer`, weak causal logic →
`root-cause-analyst`), capped at 2 loops, then escalates to you.

### The same thing in Python (no LLM, fully deterministic — good for CI)
```bash
uv run python -c "from atlas.orchestrator import run_analysis; \
r = run_analysis('Why did EMEA gross margin drop 4pts in Q2?'); \
print(r.status, '|', r.headline); print('gates:', r.gates); print(r.run_dir)"
```

### What you get: `runs/<run_id>/`
| File | Purpose |
|---|---|
| `brief.md` | Decision owner, metric, window, grain, success criteria, non-goals, **declared assumptions** |
| `profile/<source>.md` | Data-quality battery + `GO`/`NO-GO` verdict |
| `hypotheses.md` | Each branch's evidence-for / evidence-against |
| `queries/*.sql` + `*.meta.json` | Every query, content-addressed by hash |
| `evidence/*.json` | The exact result rows each number was read from |
| `findings.md` | Ranked drivers with evidence tiers + the decomposition |
| `validation.md` | Red-team re-derivation + attack results |
| `narrative.md` | SCQA / pyramid answer for the decision owner |
| `deck.pptx` + `speaker_notes.md` | The deliverable + 60–90s notes per slide |
| `provenance.json` | The ledger: `claim_id → value → query_hash → result_hash → slide` |
| `retro.md` | Gate outcomes, budget, lessons written |

---

## 3. Use a single phase (you rarely need the whole pipeline)

Every stage has a **slash command** (agent-driven) *and* an underlying **Python/script**
(deterministic). Pick the altitude you need.

| I want to… | Slash command | Underlying building block |
|---|---|---|
| Check a source is trustworthy | `/profile emea_finance_csv` | `atlas.lib.profiling.profile_table` + `verdict_for` |
| Just the root cause (skip framing) | `/rca gross_margin "Q2 vs Q1"` | `metric-decomposition/scripts/decompose.py` · `decompose_margin` |
| **Just make a chart** | *(see snippet below)* | `atlas.lib.deck_pptx.build_deck` + `Chart`, or the `dataviz` skill |
| Rebuild/ship a deck from a past run | `/deck <run_id>` | `build_deck` |
| Validate a finding independently | `/validate <run_id>` | `validation-protocol/scripts/rederive.py` |
| Check a past finding still holds | `/replay <run_id>` | `QueryStore.verify` |
| A one-off lookup, no deck | `/quick "total EMEA revenue in Q2"` | one `Connector.run()` |
| Redo just one stage after feedback | `/explore` · `/diagnose` · `/narrative <run_id>` | re-runs Wave C / D / E on stored artefacts |

### "Just make a chart" — standalone, no pipeline
The deck builder's `Chart` + one-slide `DeckSpec` is the fastest honest path to a
provenance-clean chart in a `.pptx`:

```bash
uv run python - <<'PY'
from atlas.lib.deck_pptx import Chart, Slide, DeckSpec, build_deck

spec = DeckSpec(
    title="EMEA gross margin fell 4pts in Q2",
    subtitle="Q2 vs Q1", decision_owner="VP Finance, EMEA",
    slides=[Slide(
        kind="insight",
        title="Gross margin dropped from 60.0% to 56.0%",
        chart=Chart("column", ["Q1", "Q2"], {"Gross margin %": [60.0, 56.0]},
                    title="EMEA gross margin"),
        speaker_notes="A 4-point drop, entirely explained by mix.",
    )],
)
build_deck(spec, "chart.pptx", "chart_notes.md")
print("wrote chart.pptx")
PY
```
`Chart(kind, categories, series, title)` supports `kind` = `"column" | "bar" | "line"`.
For a standalone image (PNG/SVG/HTML) rather than a slide, invoke the **`dataviz`
skill** — it produces accessible, theme-aware charts in any medium.

### Root cause in one line
```bash
uv run python .claude/skills/metric-decomposition/scripts/decompose.py emea_finance_csv EMEA Q1 Q2
# → exact mix / rate / interaction split + Simpson's-paradox check, as JSON
```

---

## 4. Commands reference

All live in `.claude/commands/`. Type `/<name>` in Claude Code; `$ARGUMENTS` is passed through.

| Command | Argument | Example |
|---|---|---|
| `/analyze` | `"<question>"` | `/analyze "Why did EMEA gross margin drop 4pts in Q2?"` |
| `/quick` | `"<question>"` | `/quick "total EMEA revenue in Q2"` |
| `/rca` | `<metric> <window>` | `/rca gross_margin "Q2 vs Q1"` |
| `/profile` | `<source>` | `/profile emea_finance_csv` |
| `/connect` | `<source>` | `/connect prod_pg` |
| `/explore` | `<run_id>` | re-run exploration only |
| `/diagnose` | `<run_id>` | re-run decomposition + stats |
| `/narrative` | `<run_id>` | rewrite the narrative |
| `/deck` | `<run_id>` | rebuild the deck |
| `/validate` | `<run_id>` | re-run the red-team |
| `/replay` | `<run_id>` | re-run stored queries vs current data |
| `/retro` | `<run_id>` | force a retrospective |
| `/lessons` | `[tag]` | `/lessons metric:gross_margin` |
| `/runs` | `[run_id]` | list / inspect / compare pipeline runs |
| `/resume` | `<run_id>` | resume an interrupted run (no re-query) |
| `/route` | `"<question>"` | classify L1–L5 and route to the cheapest path |
| `/business` | `[glossary\|term]` | browse org knowledge + metric ownership |
| `/metrics` | `[metric]` | metric dictionary (locked formula + context) |
| `/log-correction` | `<wrong> -> <right>` | log a correction; promotable to code |
| `/cohort` | `<source>` | retention / vintage / LTV |
| `/forecast` | `<metric> [horizon]` | trend + anomaly + seasonality + forecast |
| `/size` | `"<finding>"` | opportunity sizing + tornado |
| `/experiment` | `<base> <mde>` | A/B sample size, power, guardrails |
| `/export` | `<fmt> <run_id>` | HTML / PDF / Slack / email / exec |
| `/setup` | | onboarding interview (role, data, context) |

---

## 5. Agents — the analytics team

12 specialists in `.claude/agents/`. Each runs in its **own context window** and returns
**summaries + artefact paths, never raw dumps** — that isolation is the whole point.

| Agent | Owns | Tier |
|---|---|---|
| `requirements-analyst` | Vague ask → decision-grade brief | Opus |
| `source-profiler` | Connect, profile, `GO`/`NO-GO` verdict | Sonnet |
| `semantic-architect` | Resolve metrics vs `metrics.yaml` or escalate | Opus |
| `sql-engineer` | Dialect-aware, cost-aware, hashed queries | Sonnet |
| `explorer` | One hypothesis branch, isolated + budgeted | Sonnet |
| `root-cause-analyst` | Decomposition, mix-vs-rate, driver tree | Opus |
| `statistician` | Significance, power, seasonality, CIs | Opus |
| `red-team-validator` | Independent re-derivation + attacks; **veto** | Opus |
| `narrative-writer` | SCQA / pyramid for the decision owner | Opus |
| `deck-builder` | Fixed-skeleton `.pptx` + speaker notes | Sonnet |
| `stakeholder-simulator` | 5 hardest exec questions | Opus |
| `retrospective-agent` | Lessons + hard-artefact promotion | Opus |
| `cohort-analyst` | Retention curves, vintage, cohort LTV | Sonnet |
| `forecaster` | Trend / anomaly / seasonality / forecast with a band | Sonnet |
| `opportunity-sizer` | Impact sizing + tornado sensitivity | Opus |
| `experiment-designer` | A/B sample size, power, guardrails, decision rule | Opus |
| `comms-drafter` | Slack / email / exec comms (provenance-checked) | Sonnet |

**Invoke one directly** (skip the pipeline) with a natural request, e.g.
`> use the source-profiler subagent to profile emea_finance_csv`, or via the Task tool
naming the `subagent_type`. **Hand-off contract:** raw artefacts go to
`runs/<run_id>/`; agents pass back only summaries + provenance IDs; defects route to the
owning agent (see `atlas/lib/gates.py::ROUTING`).

---

## 6. Skills — capability, loaded on demand

10 skills in `.claude/skills/`. A skill loads when your task matches its description, or
when you invoke it by name. **Guidance skills** shape judgement; **script skills** carry
runnable, deterministic tools.

| Skill | Type | Use it for |
|---|---|---|
| `metric-decomposition` | script | mix/rate/interaction, contribution, Simpson |
| `data-connectors` | script | register/test a source |
| `validation-protocol` | script | independent re-derivation + veto criteria |
| `memory-protocol` | script | write/dedup/retrieve/promote lessons |
| `data-profiling` | guidance | the profiling battery + reading the verdict |
| `statistical-testing` | guidance | which test when, power, seasonality |
| `root-cause-playbooks` | guidance | named playbooks (margin, churn, funnel, …) |
| `sql-dialects` | guidance | per-warehouse syntax + cost patterns |
| `narrative-craft` | guidance | pyramid/SCQA, claim-not-label titles |
| `deck-standards` | guidance | layout grid, chart selection, appendix rules |

**Runnable script tools:**
```bash
# decomposition (JSON)
uv run python .claude/skills/metric-decomposition/scripts/decompose.py emea_finance_csv EMEA Q1 Q2
# test a connection
uv run python .claude/skills/data-connectors/scripts/conn_test.py emea_finance_csv
# independent re-derivation vs a claimed headline
uv run python .claude/skills/validation-protocol/scripts/rederive.py emea_finance_csv EMEA Q1 Q2 60.0 56.0
# lesson store
uv run python .claude/skills/memory-protocol/scripts/lesson.py find metric:gross_margin
```

---

## 7. Memory & the learning loop

Atlas is designed so a mistake made **once** is prevented **structurally**, not just
remembered. Memory lives in `memory/`.

- **Lesson** (`memory/lessons.jsonl`): `id, trigger, tags, what_went_wrong, rule,
  run_id, times_prevented`. Human index in `lessons.md`.
- **Failure fingerprint** (`memory/failures.jsonl`): `sha256(source|metric|failure_class)`.
  Before a wave, matching lessons are injected into the relevant agent's prompt.
- **Source quirks** (`memory/quirks/<source>.md`): per-source gotchas injected into the
  profiler and sql-engineer.

Workflow:
```bash
# record a lesson (semantic-dedup blocks near-duplicates)
uv run python .claude/skills/memory-protocol/scripts/lesson.py add '{"tags":["metric:gross_margin","class:mix-vs-rate"],"what_went_wrong":"called a mix shift a cost problem","rule":"always decompose mix vs rate before naming a cost cause"}'
# retrieve by fingerprint
uv run python .claude/skills/memory-protocol/scripts/lesson.py retrieve emea_finance_csv gross_margin mix-vs-rate
# fire it (increments times_prevented; prompts promotion at 2)
uv run python .claude/skills/memory-protocol/scripts/lesson.py fire L-0001
```
Or from Claude Code: `/lessons [tag]` to search, `/retro <run_id>` to force a
retrospective.

**"Fires twice ⇒ becomes code."** The honest guarantee table:

| Lesson class | Enforcement | Guarantee |
|---|---|---|
| Metric definition | Locked in `atlas/semantic/metrics.yaml` | **Mechanical** |
| Unsafe write | Rule in `.claude/hooks/pre_tool_use.py` | **Mechanical** |
| Scan-budget blowout | Byte gate in the hook | **Mechanical** |
| Repeated clarification | Stored default in the brief template | **Mechanical** |
| Source quirk | Assertion in `quirks/<source>.md` | Mechanical *if asserted* |
| Analytical mistake | Prompt-injected lesson | **Best-effort** (until promoted) |

Only promoted artefacts are guaranteed. Plain lessons are a strong nudge, not a hard
stop — and Atlas never claims otherwise.

---

## 8. Provenance & gates

Every number is a link in a chain:
```
run_id → claim_id → query_hash → result_hash → slide_number
```
`atlas/lib/provenance.py` stores it; `provenance.json` persists it per run. The gates
(`atlas/lib/gates.py`) block progress: **G1** profiling GO · **G2** metrics resolved ·
**G3** red-team PASS + re-derivation in tolerance · **G4** no orphan numbers on any
slide · **G5** every hard stakeholder question answerable.

---

## 9. Connect a warehouse (dormant → live)

Local CSV/Excel works out of the box via DuckDB. Warehouse adapters are **built but
dormant** until you supply credentials:

1. Uncomment the source template in `atlas/connectors/sources.yaml` and set its
   `*_env` keys to the **names** of env vars (never values).
2. Put the values in `.env` (use a **read-only** DB role) and
   `uv pip install -e ".[warehouse]"`.
3. `/connect <source>` to verify reachable / read-only / latency.

Atlas prefers an **official MCP server** where a mature one exists (Snowflake,
Databricks, BigQuery toolbox), falling back to documented Python drivers (Postgres →
`psycopg2`, files → DuckDB). Read-only is enforced at both the connector and the hook.

> Status: Postgres adapter is implemented (untested until a live instance exists);
> Snowflake/BigQuery/Databricks ship as skeletons (Phase 7). Google Slides export is a
> Phase-8 stub — `.pptx` is always the source of truth.

---

## 10. Testing & verification

```bash
uv run pytest -q                     # 47 tests across connectors, provenance, gates,
                                     # decomposition, deck, and the end-to-end pipeline
```
End-to-end smoke test in one line:
```bash
uv run python -c "from atlas.orchestrator import run_analysis; r=run_analysis('Why did EMEA gross margin drop 4pts in Q2?'); print(r.status, r.headline)"
```

---

## Repo map

```
CLAUDE.md               # project constitution (always in context)
atlas/
  orchestrator.py       # deterministic wave scheduler + gates
  config.py             # paths, budgets, tolerances, secrets loading
  connectors/           # base + registry + csv_duckdb (live) + warehouse adapters
  semantic/             # locked metrics.yaml, dimensions, joins + resolver
  lib/                  # provenance, query_store, decomposition, stats, profiling,
                        # gates, budget, sqlguard, deck_pptx, deck_gslides
.claude/
  agents/               # 12 sub-agent definitions
  commands/             # 13 slash commands
  skills/               # 10 skills (4 with runnable scripts)
  hooks/                # read-only guard, provenance log, retro trigger
memory/                 # lessons, failure fingerprints, source quirks
runs/<run_id>/          # every artefact from one question
tests/                  # fixtures + 47 tests
```

---

### Honest limits
Local CSV/Excel is the live path today. Warehouse adapters need credentials (and some
are skeletons). Prompt-injected lessons are best-effort until promoted. Google Slides
export needs a one-time OAuth. Atlas would rather tell you these than pretend.
