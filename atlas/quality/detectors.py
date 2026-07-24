"""Issue detection: run every registered repair module's detector over a table.

Returns a flat, deterministically-ordered list of Issues. Detection is delegated
to the modules so detection and repair never drift apart. Every probe runs
through the guarded, provenance-stamped `Connector.run()`.
"""
from __future__ import annotations

from atlas.connectors.base import Connector, TableRef
from atlas.quality.modules import all_modules
from atlas.quality.modules.base import SEVERITY_RANK, Issue
from atlas.quality.rules_loader import module_enabled


def superseded_columns(schema) -> set[str]:
    """Raw columns that already have a `<col>_Clean` sibling in the schema.

    On a clean layer these are superseded by their repaired counterpart, so they
    are not re-flagged as defects (downstream reads the *_Clean column). On a raw
    table this is empty, so detection is unchanged (backward compatible)."""
    names = {c.name for c in schema.columns}
    return {c.name for c in schema.columns if f"{c.name}_Clean" in names}


def detect_issues(con: Connector, table: TableRef) -> list[Issue]:
    """Detect all data-quality issues on `table`, most-severe first."""
    schema = con.get_schema(table)
    superseded = superseded_columns(schema)
    issues: list[Issue] = []
    for mod in all_modules():
        if not module_enabled(mod.id):
            continue
        issues.extend(mod.detect(con, table, schema))
    # Drop issues on columns already repaired into a *_Clean sibling.
    issues = [i for i in issues if i.column not in superseded]
    # Stable, severity-first ordering (module id + column break ties).
    issues.sort(key=lambda i: (-SEVERITY_RANK.get(i.severity, 0), i.module_id, i.column or ""))
    return issues


def critical_issues(issues: list[Issue]) -> list[Issue]:
    """HIGH-severity, non-structural issues — the ones that block readiness."""
    return [i for i in issues if i.severity == "HIGH" and not i.structural]
