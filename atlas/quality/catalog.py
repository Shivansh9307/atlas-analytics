"""Enterprise data catalog.

Every connected dataset gets a catalog entry: owner, quality score, certification
status, last refresh, business description, tags, schema, and lineage pointer.
Persisted under clean_layers/_catalog/<source>.json (runtime state) and browsable
via /catalog.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from atlas.config import PATHS
from atlas.connectors.base import Connector, TableRef
from atlas.quality import clean_layer as cl
from atlas.quality.score import score_table


def _catalog_dir() -> Path:
    return PATHS.clean / "_catalog"


def _entry_path(source: str) -> Path:
    return _catalog_dir() / f"{source}.json"


# Certification is a function of the quality band + whether a clean layer exists.
def _certification(score: float, has_clean: bool) -> str:
    if score >= 90:
        return "Certified" if has_clean or score >= 95 else "Certified (raw)"
    if score >= 75:
        return "Provisional"
    return "Uncertified"


def build_entry(con: Connector, table: TableRef, source: str, *,
                owner: str = "", description: str = "", tags: list[str] | None = None,
                persist: bool = True) -> dict:
    rep = score_table(con, table)
    man = cl.load_manifest(source)
    has_clean = bool(man and man.get("transforms"))
    quirks = PATHS.quirks / f"{source}.md"
    entry = {
        "source": source,
        "table": table.name,
        "owner": owner or "unassigned",
        "quality_score": rep.overall_score,
        "business_readiness": rep.business_readiness,
        "certification": _certification(rep.overall_score, has_clean),
        "last_refresh": rep.freshness,
        "description": description or (quirks.read_text().splitlines()[0].lstrip("# ")
                                       if quirks.exists() else ""),
        "tags": tags or [],
        "schema": {c.name: c.dtype for c in con.get_schema(table).columns},
        "semantic_layer": (man or {}).get("clean_table") if has_clean else None,
        "critical_issues": rep.critical_count,
        "cataloged_at": datetime.now(timezone.utc).isoformat(),
    }
    if persist:
        p = _entry_path(source)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entry, indent=2))
    return entry


def get_entry(source: str) -> dict | None:
    p = _entry_path(source)
    return json.loads(p.read_text()) if p.exists() else None


def list_catalog() -> list[dict]:
    d = _catalog_dir()
    if not d.exists():
        return []
    entries = [json.loads(p.read_text()) for p in d.glob("*.json")]
    return sorted(entries, key=lambda e: e.get("quality_score", 0), reverse=True)
