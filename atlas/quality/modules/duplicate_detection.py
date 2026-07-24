"""Duplicate Detection: fully-duplicate rows -> a deduplicated clean layer."""
from __future__ import annotations

from atlas.connectors.base import Connector, TableRef, TableSchema
from atlas.quality.modules.base import BusinessImpact, Issue, Repair, RepairModule, register


@register
class DuplicateDetection(RepairModule):
    id = "duplicate_detection"
    dimension = "uniqueness"

    def detect(self, con: Connector, table: TableRef, schema: TableSchema) -> list[Issue]:
        tname = table.qualified()
        total = con.run(f"SELECT count(*) AS n FROM {tname}").rows[0]["n"] or 0
        distinct = con.run(
            f"SELECT count(*) AS n FROM (SELECT DISTINCT * FROM {tname})"
        ).rows[0]["n"] or 0
        dups = total - distinct
        if total == 0 or dups == 0:
            return []
        return [Issue(
            module_id=self.id, dimension=self.dimension, column=None,
            severity="HIGH" if dups / total > 0.01 else "MED", confidence=1.0,
            description=f"{dups} fully-duplicate row(s) of {total}; aggregates are inflated.",
            detail={"duplicate_rows": int(dups), "total": int(total)},
        )]

    def plan(self, con, table, schema, issue) -> Repair | None:
        bi = BusinessImpact(
            problem="Duplicate rows present",
            business_risk="Sums and counts are over-stated; every total is wrong.",
            impact="HIGH",
            recommendation="Deduplicate the clean layer with SELECT DISTINCT.",
            confidence=1.0,
        )
        return Repair(
            module_id=self.id, column=None, clean_column=None,
            sql_expression=None,  # row-level: the clean view SELECTs DISTINCT
            pandas_code="df = df.drop_duplicates()",
            confidence=1.0, business_impact=bi,
            rows_affected=int(issue.detail["duplicate_rows"]), row_level=True,
            rollback="Rebuild the clean view without DISTINCT (raw rows untouched).",
            notes="Deduplication applies at the row set, not a single column.",
        )
