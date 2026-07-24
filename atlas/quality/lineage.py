"""Data lineage: trace every metric back through the layers.

Source → Transformation (clean layer) → Semantic Layer → SQL (query_store) →
Dashboard/Deck. Reuses the existing provenance chain (run_id → claim_id →
query_hash → result_hash → slide) so lineage is grounded in real stored artefacts,
not a hand-drawn diagram.
"""
from __future__ import annotations

from atlas.quality import clean_layer as cl


def build_lineage(source: str, *, base_table: str, clean_table: str | None = None,
                  provenance: list[dict] | None = None) -> dict:
    """Assemble the lineage graph for a source / run.

    `provenance` is the ProvenanceLedger claims (each: claim_id, query_hash, ...).
    """
    man = cl.load_manifest(source)
    transforms = [t for t in (man or {}).get("transforms", []) if t.get("enabled", True)]
    stages = [
        {"stage": "source", "name": source, "detail": base_table},
        {"stage": "transformation", "name": "clean layer",
         "detail": [f"{t['module_id']}→{t.get('clean_column') or 'DISTINCT'}" for t in transforms]},
        {"stage": "semantic_layer", "name": clean_table or (man or {}).get("clean_table") or base_table},
    ]
    if provenance:
        stages.append({"stage": "sql", "name": "queries",
                       "detail": [{"claim": c.get("claim_id"), "query_hash": c.get("query_hash")}
                                  for c in provenance]})
        stages.append({"stage": "deliverable", "name": "deck",
                       "detail": [c.get("claim_id") for c in provenance
                                  if c.get("slide_number") is not None]})
    return {"source": source, "stages": stages}


def render_lineage(lin: dict) -> str:
    lines = [f"# Lineage — {lin['source']}", ""]
    for s in lin["stages"]:
        detail = s.get("detail")
        lines.append(f"- **{s['stage']}**: {s['name']}"
                     + (f" — {detail}" if detail else ""))
    return "\n".join(lines)
