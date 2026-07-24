---
description: Run the full Atlas pipeline on a business question and ship a validated, provenance-stamped deck.
argument-hint: "\"<business question>\""
---

Run the full Atlas analytics pipeline for: **$ARGUMENTS**

Follow the constitution in `CLAUDE.md`. Orchestrate the waves; the deterministic
numeric backbone lives in `atlas/orchestrator.py` (use it — do not recompute
numbers by hand), while you supply the reasoning and prose via the sub-agents.

Execute in order, respecting gates and full-auto (stop only on hard failure, a
gate past its rework cap, or a projected scan over budget):

1. **Wave A** — spawn `source-profiler` per registered live source (parallel).
   GATE 1: need ≥1 GO.
2. **Wave B** — `requirements-analyst` writes the brief; `semantic-architect`
   locks metric definitions against `atlas/semantic/metrics.yaml`. GATE 2.
3. **Wave C** — spawn 3–6 `explorer` agents in parallel, one hypothesis each,
   isolated contexts + hard per-branch budget.
4. **Wave D** — `root-cause-analyst` decomposes and ranks; `statistician` tests.
5. **Wave E** — `red-team-validator` (independent re-derivation + attacks) runs
   while `narrative-writer` drafts. GATE 3 blocks the deck until PASS.
6. **Wave F** — `deck-builder` builds `deck.pptx` (+ Slides attempt). GATE 4 (no
   orphan numbers) then `stakeholder-simulator`. GATE 5. Max 2 revision loops.
7. **Wave G** — `retrospective-agent` writes lessons and promotes repeats.

Fastest path to a correct end-to-end run on the local fixture:
`uv run python -c "from atlas.orchestrator import run_analysis; r=run_analysis('$ARGUMENTS'); print(r.status, r.headline, r.run_dir)"`

Then report: the one-sentence headline, the gate results, the `run_id`, and the
path to `runs/<run_id>/deck.pptx`. If BLOCKED, report what is blocking and what
Atlas needs — never a degraded deck.
