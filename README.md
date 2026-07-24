# Atlas — an autonomous analytics team inside Claude Code

Ask one business question in plain English; Atlas returns a validated slide deck
with speaker notes, and **every number traces back to a query you can re-run**.

```
/analyze "Why did EMEA gross margin drop 4pts in Q2?"
```

## Quickstart

```bash
uv venv --python 3.13.9
uv pip install -e ".[dev]"          # core; add ".[warehouse]" / ".[deck]" / ".[llm]" later
cp .env.example .env                 # fill in only what you use; .env is gitignored
uv run pytest -q                     # 45+ tests, all green
```

Run the full deterministic pipeline on the bundled fixture:

```bash
uv run python -c "from atlas.orchestrator import run_analysis; \
r = run_analysis('Why did EMEA gross margin drop 4pts in Q2?'); \
print(r.status, '|', r.headline); print(r.run_dir)"
```

Every artefact lands in `runs/<run_id>/`: `brief.md`, `profile/`, `hypotheses.md`,
`queries/*.sql`, `evidence/`, `findings.md`, `validation.md`, `narrative.md`,
`deck.pptx`, `speaker_notes.md`, `provenance.json`, `retro.md`.

## How it works
- **Constitution:** `CLAUDE.md` — non-negotiables (no fabricated numbers, read-only,
  fail loudly). Always in context.
- **Sub-agents:** `.claude/agents/` — 12 isolated specialists (frame → profile →
  semantic → explore → decompose → test → red-team → narrate → deck → simulate →
  retro).
- **Backbone:** `atlas/` — deterministic connectors, provenance ledger, query store,
  decomposition/stats maths, gates, budgets, deck builder. Numbers and gates live
  here so they are testable without any LLM call.
- **Skills:** `.claude/skills/` — decomposition, profiling, stats, validation,
  deck standards, narrative craft, memory protocol, SQL dialects, playbooks.
- **Memory:** `memory/` — lessons + failure fingerprints; a lesson that fires twice
  is promoted to a hard artefact.

## Data sources
Live today: **local CSV / Excel** via DuckDB. Postgres / Snowflake / BigQuery /
Databricks adapters are built but dormant — populate their env vars in `.env`,
install `".[warehouse]"`, and `/connect <source>`.

## Guarantees, honestly
Mechanical (guaranteed): locked metric definitions, the read-only hook + connector
guard, the scan-byte budget, provenance Gate 4, twice-asked-clarification defaults.
Best-effort (a strong nudge, not a hard stop): prompt-injected analytical lessons —
until they fire twice and get promoted to code.
