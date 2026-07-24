---
description: Detect, plan, preview, apply, undo, and audit data-quality repairs on a source (semantic clean layer; raw stays untouched).
argument-hint: "<source> [--preview | --apply | --undo | --history]"
---

Run the **Data Quality Copilot** on source **$ARGUMENTS**. Parse the flag from the
arguments (default = plan). Raw data is never modified — repairs create a
`<table>_clean` semantic layer with `*_Clean` columns.

Delegate to the `data-quality-copilot` agent, or run directly. Every probe routes
through `Connector.run()` (read-only, provenance-stamped); the clean layer is
materialised via the connector's dedicated `materialize_clean()` path, never
through source-facing SQL.

**Plan** (no flag) — detect issues, score quality, list proposed repairs with
confidence + business impact:
```
uv run python -c "from atlas.connectors.registry import Registry; from atlas.connectors.base import TableRef; from atlas.quality import clean_layer as cl; from atlas.quality.score import score_table; c=Registry().connector('<source>'); t=TableRef(c.table_name); p=cl.build_plan(c,t); s=score_table(c,t); print('score', s.overall_score, s.business_readiness); [print(x.module_id, x.column, '->', x.clean_column, 'conf', x.confidence, x.approved_by) for x in p.transforms]"
```

**`--preview`** — before→after quality score, rows affected, per-column samples,
and the generated DDL:
```
uv run python -c "from atlas.connectors.registry import Registry; from atlas.connectors.base import TableRef; from atlas.quality import clean_layer as cl; c=Registry().connector('<source>'); pv=cl.preview(c, TableRef(c.table_name)); print('score', pv.before.overall_score, '->', pv.after.overall_score, '(', pv.score_delta(), ')'); [print(s['module_id'], s['column'], s['examples'][:3]) for s in pv.samples]"
```

**`--apply`** — materialise `<table>_clean` and persist the manifest + audit trail.
High-confidence repairs auto-apply; low-confidence ones (e.g. calendar-vs-fiscal
`Quarter`) need `approve=True`. NEVER overwrites the original:
```
uv run python -c "from atlas.connectors.registry import Registry; from atlas.connectors.base import TableRef; from atlas.quality import clean_layer as cl; c=Registry().connector('<source>'); r=cl.apply(c, TableRef(c.table_name)); print('clean table:', r.clean_table); print('applied:', [t.module_id for t in r.applied]); print('needs approval (skipped):', [t.module_id for t in r.skipped]); print('score', r.before.overall_score, '->', r.after.overall_score)"
```
Pass `approve=True` to `cl.apply(...)` to also apply the flagged repairs after the
user confirms.

**`--undo`** — roll back the most recent repair and re-materialise:
```
uv run python -c "from atlas.connectors.registry import Registry; from atlas.quality import clean_layer as cl; c=Registry().connector('<source>'); print(cl.undo(c, '<source>'))"
```

**`--history`** — timestamp, repair, approval, rows affected, user:
```
uv run python -c "from atlas.quality import clean_layer as cl; import json; print(json.dumps(cl.history('<source>'), indent=2))"
```

Report the score delta, which repairs applied vs. need approval, and the business
impact of the top issues. State clearly that the raw source is unchanged and which
`*_Clean` columns downstream analysis will use.
