"""Schema drift detection.

Snapshots a source's schema on connect; on the next connect, diffs it to surface
renamed / removed / added columns and datatype changes, with mapping suggestions
so a downstream query or clean layer can be re-pointed rather than silently break.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from atlas.config import PATHS
from atlas.connectors.base import Connector, TableRef


def _snap_path(source: str) -> Path:
    return PATHS.clean / "_schema" / f"{source}.json"


def _current(con: Connector, table: TableRef) -> dict[str, str]:
    return {c.name: c.dtype for c in con.get_schema(table).columns}


@dataclass
class Drift:
    added: dict[str, str] = field(default_factory=dict)          # name -> dtype
    removed: dict[str, str] = field(default_factory=dict)
    dtype_changed: dict[str, list[str]] = field(default_factory=dict)  # name -> [old, new]
    renamed_suggestions: list[dict] = field(default_factory=list)      # {from,to,dtype}

    @property
    def has_drift(self) -> bool:
        return bool(self.added or self.removed or self.dtype_changed)

    def as_dict(self) -> dict:
        return {"added": self.added, "removed": self.removed,
                "dtype_changed": self.dtype_changed,
                "renamed_suggestions": self.renamed_suggestions,
                "has_drift": self.has_drift}


def snapshot_schema(con: Connector, table: TableRef, source: str) -> Path:
    p = _snap_path(source)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "source": source, "table": table.name,
        "columns": _current(con, table),
        "ts": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    return p


def detect_drift(con: Connector, table: TableRef, source: str,
                 *, update: bool = False) -> Drift | None:
    """Diff the current schema against the stored snapshot. None if no snapshot yet."""
    p = _snap_path(source)
    if not p.exists():
        if update:
            snapshot_schema(con, table, source)
        return None
    prev = json.loads(p.read_text()).get("columns", {})
    cur = _current(con, table)

    added = {c: dt for c, dt in cur.items() if c not in prev}
    removed = {c: dt for c, dt in prev.items() if c not in cur}
    changed = {c: [prev[c], cur[c]] for c in cur if c in prev and prev[c] != cur[c]}

    # Rename heuristic: a removed and an added column sharing a dtype.
    suggestions = []
    used = set()
    for rname, rdt in removed.items():
        for aname, adt in added.items():
            if adt == rdt and aname not in used:
                suggestions.append({"from": rname, "to": aname, "dtype": adt})
                used.add(aname)
                break

    if update:
        snapshot_schema(con, table, source)
    return Drift(added=added, removed=removed, dtype_changed=changed,
                 renamed_suggestions=suggestions)
