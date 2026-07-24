---
description: Resume an interrupted pipeline run from the first incomplete node, reusing stored artefacts.
argument-hint: <run_id>
---

Resume the interrupted run: **$ARGUMENTS**

Atlas re-enters the DAG at the first incomplete node and **reuses everything already
done** — completed nodes are skipped, their outputs rehydrated from
`pipeline_state.json` and `provenance.json`, and no completed query is re-run.

```bash
uv run python -c "from atlas.orchestrator import run_analysis; \
r = run_analysis('', resume_run_id='$ARGUMENTS'); \
print(r.status, '|', r.headline); print(r.run_dir)"
```

Report what the resume did: which nodes re-ran vs were skipped (`r.artefacts` lists
only this session's newly-written files), the final status, and the deck path. If the
run was BLOCKED by a gate, fix the blocking condition first (see `BLOCKED.md`), then
resume. Use `/runs <run_id>` first if you're unsure where it stopped.
