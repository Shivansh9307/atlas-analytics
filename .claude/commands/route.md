---
description: Classify a question (L1–L5) and route it to the cheapest path that answers it.
argument-hint: "\"<question>\""
---

Route the question: **$ARGUMENTS**

Not every question needs the full pipeline. Classify and recommend:
```bash
uv run python -c "
from atlas.lib.router import route
import json; print(json.dumps(route('$ARGUMENTS'), indent=2))"
```

Levels: L1 lookup / L2 breakdown → `/quick`; L3 root-cause (why) → `/analyze`;
L4 forecast → `/forecast`; L5 experiment → `/experiment`. Tell the user the level, the
recommended command, and why — then offer to run it. If confidence is low, ask one
clarifying question before committing to the full pipeline.
