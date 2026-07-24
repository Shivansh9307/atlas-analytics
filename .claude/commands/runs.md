---
description: List, inspect, and compare pipeline runs and their status.
argument-hint: "[run_id]"
---

Show pipeline runs: **$ARGUMENTS** (empty = list all, newest first).

List every run with its status, question, headline, and node progress:
```bash
uv run python -c "from atlas.lib.run_state import list_runs; import json; \
print(json.dumps(list_runs(), indent=2))"
```

If a `run_id` is given, inspect it in detail — read `runs/<run_id>/pipeline_state.json`
(node-by-node status, gate results, budget snapshot) and summarise:
- overall status (COMPLETE / BLOCKED / FAILED / RUNNING)
- which nodes are OK vs incomplete (so you know where `/resume` would restart)
- the gate results and the headline
- the artefacts present in `runs/<run_id>/`

To compare two runs, diff their `provenance.json` headline claims and gate results.
If a run is BLOCKED or FAILED, point to the `BLOCKED.md` / `FAILED.md` and what it needs.
