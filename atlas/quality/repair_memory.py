"""Repair memory: remember approved repairs so future connects reuse them.

Stored beside the prose quirks as `memory/quirks/<source>.repairs.jsonl` (the
corrections.py JSONL idiom). Records approved repairs, the business rule they
encode, and the country/date mappings used — so a re-connect can re-propose (or
auto-apply) known-good repairs without re-deriving them.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from atlas.config import PATHS


def _path(source: str) -> Path:
    return PATHS.quirks / f"{source}.repairs.jsonl"


def _load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] \
        if path.exists() else []


def remember_repairs(source: str, transforms: list, *, run_id: str = "",
                     user: str = "operator") -> int:
    """Persist approved repairs (idempotent per module+column). Returns #new."""
    p = _path(source)
    rows = _load(p)
    seen = {(r["module_id"], r.get("column")) for r in rows}
    ts = datetime.now(timezone.utc).isoformat()
    added = 0
    for t in transforms:
        key = (t.module_id, t.column)
        if key in seen:
            continue
        rows.append({
            "module_id": t.module_id, "column": t.column,
            "clean_column": t.clean_column, "sql_expression": t.sql_expression,
            "confidence": round(t.confidence, 4), "approved_by": t.approved_by,
            "rows_affected": t.rows_affected, "run_id": run_id, "user": user, "ts": ts,
        })
        seen.add(key)
        added += 1
    if added:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return added


def recall_repairs(source: str) -> list[dict]:
    """Previously-approved repairs for a source (for reuse on re-connect)."""
    return _load(_path(source))


def known_repair_columns(source: str) -> set[str]:
    return {r["column"] for r in recall_repairs(source) if r.get("column")}
