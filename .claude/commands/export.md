---
description: Export a completed run to more formats — HTML, PDF, Slack, email, or exec summary.
argument-hint: <format[,format]> <run_id>
---

Export run to: **$ARGUMENTS**

Formats: `html` (self-contained, portable), `pdf` (best-effort, needs the [deck]
extra), `slack`, `email`, `exec`. `.pptx` is always the source of truth; these are
additional renderings of the SAME validated findings.

```bash
uv run python -c "
from atlas.lib.exporters import export_run
import json; print(json.dumps(export_run('<run_id>', formats=['<f1>','<f2>']), indent=2))"
```

**Gate 4 applies to every format** — each export re-checks that every number resolves
in the provenance ledger and raises `OrphanNumberError` otherwise. Report the written
paths. If PDF is `deferred`, the HTML is the portable source of truth (install the
`[deck]` extra to enable weasyprint PDF).
