---
description: Browse the enterprise data catalog — per-source owner, quality score, certification, freshness, tags, schema, and lineage.
argument-hint: "[<source>]"
---

Browse the **enterprise data catalog**. With no argument, list every cataloged
dataset; with a source, show its full entry and refresh it.

**List all datasets** (newest quality first):
```
uv run python -c "from atlas.quality.catalog import list_catalog; import json; [print(e['source'], '|', e['quality_score'], e['certification'], '|', e['business_readiness'], '| owner', e['owner']) for e in list_catalog()] or print('(empty — build an entry with /catalog <source>)')"
```

**Show + refresh one source** (also snapshots its schema for drift detection):
```
uv run python -c "from atlas.connectors.registry import Registry; from atlas.connectors.base import TableRef; from atlas.quality import catalog, drift; c=Registry().connector('$ARGUMENTS'); t=TableRef(c.table_name); e=catalog.build_entry(c, t, '$ARGUMENTS'); import json; print(json.dumps(e, indent=2)); d=drift.detect_drift(c, t, '$ARGUMENTS', update=True); print('drift:', d.as_dict() if d else 'first snapshot recorded')"
```

Report the quality score, certification status, owner, freshness, the semantic
clean layer (if any), and any schema drift since the last snapshot (renamed /
added / removed columns with mapping suggestions). Certification: **Certified**
(score ≥90 with a clean layer), **Provisional** (≥75), **Uncertified** (<75).
