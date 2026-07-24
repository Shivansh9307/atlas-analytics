"""Business Impact Engine.

Turns a detected Issue into the spec's Problem / Business Risk / Impact /
Recommendation / Confidence statement by asking the owning module to plan the
repair (the BusinessImpact lives on the Repair). Detection and business framing
therefore stay coupled to the module that understands the defect.
"""
from __future__ import annotations

from atlas.connectors.base import Connector, TableRef
from atlas.quality.modules.base import REGISTRY, BusinessImpact, Issue


def impact_for_issue(con: Connector, table: TableRef, issue: Issue) -> BusinessImpact:
    """The BusinessImpact for one issue (via its module's plan)."""
    mod = REGISTRY.get(issue.module_id)
    if mod is not None:
        schema = con.get_schema(table)
        repair = mod.plan(con, table, schema, issue)
        if repair is not None:
            return repair.business_impact
    # Fallback: a generic statement (should be rare — every module plans an impact).
    return BusinessImpact(
        problem=issue.description,
        business_risk="Unassessed — no repair module produced an impact.",
        impact=issue.severity,
        recommendation="Review manually.",
        confidence=issue.confidence,
    )


def impact_summary(con: Connector, table: TableRef, issues: list[Issue]) -> list[dict]:
    """Business-impact rows for a list of issues (for /clean and reports)."""
    out = []
    for i in issues:
        bi = impact_for_issue(con, table, i)
        row = bi.as_dict()
        row["column"] = i.column
        row["severity"] = i.severity
        row["module_id"] = i.module_id
        out.append(row)
    return out
