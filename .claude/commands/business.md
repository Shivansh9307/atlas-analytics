---
description: Browse organization knowledge — glossary, products, teams, and metric ownership.
argument-hint: "[glossary|products|teams|<term>]"
---

Browse business knowledge: **$ARGUMENTS** (empty = overview).

Read `atlas/knowledge/glossary.yaml` and `business.yaml` via the loader:
```bash
uv run python -c "
from atlas.knowledge import load_glossary, load_business
import json
print('ORG:', load_business().get('organization', {}).get('name'))
print('TEAMS:', [t['name'] for t in load_business().get('teams', [])])
print('TERMS:', [t.term for t in load_glossary().values()])
"
```

- `glossary` — list all terms with definitions.
- `products` / `teams` — from `business.yaml`, including which team **owns** which metric
  and its decision owner.
- a specific `<term>` — resolve it (`atlas.knowledge.resolve_term`) and show its
  definition, category, and linked metric.

This is context, not formula authority — canonical metric math lives in
`atlas/semantic/metrics.yaml` (browse it with `/metrics`).
