---
name: business-knowledge
description: The organization knowledge layer — glossary, metric dictionary, ownership, query archaeology, corrections, and the session context bundle. Use to resolve business terms, find whose metric it is, reuse proven SQL, or load context before analysis.
---

# Business knowledge

Atlas's "teach it your business" layer. Formula authority stays in
`atlas/semantic/metrics.yaml`; this adds the human context around it.

## Glossary & org (`atlas/knowledge/`)
- `resolve_term(text)` → a `Term` (definition, category, linked metric) by name/alias.
- `metric_dictionary()` → locked formula + owner team + decision owner + `watch_for`.
- `decision_owner_for(metric)` → the accountable role. Browse via `/business`, `/metrics`.

## Query archaeology (`atlas/lib/query_archive.py`)
Before authoring new SQL, retrieve a proven pattern:
```python
from atlas.lib.query_archive import retrieve, archive
hits = retrieve(source="emea_finance_csv", metric="gross_margin",
                intent_tags=["margin", "period-compare"])
```
Validated headline queries are archived automatically on a successful run. Reusing a
query increments `times_reused`; identical SQL is deduped by the QueryStore hash.

## Context loader (`atlas/lib/context_loader.py`)
`load_context(source, connector).render()` → a markdown bundle (schema, quirks,
glossary, metric dictionary, recent lessons, proven-query count) to inject at session
start or into an agent prompt.

## Corrections & miss-rate (`atlas/lib/corrections.py`)
- `log_correction(what, correct, cls=..., scope=...)` — `/log-correction`. Classes
  `metric-definition`/`source-quirk`/`unsafe-write`/`filter-leakage` are **promotable**
  to a mechanical guarantee (the returned `promotion_hint` says how). `analytical`
  stays best-effort.
- `log_miss(kind, prevented=...)` + `miss_rate()` — honest instrumentation of whether
  the learning loop is actually improving. Not a vanity metric.

## Rule
Resolve terms and reuse proven SQL before writing new. A promotable correction that
recurs MUST become code (locked metric / quirk assertion / hook rule) — only then is
it guaranteed. See [[memory-protocol]].
