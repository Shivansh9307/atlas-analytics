"""Null Classification: separate by-design (structural) nulls from defects.

A column that is almost entirely NULL is usually structural (populated only for a
sub-population, e.g. Churn_Reason only for churned customers). Flagging it as a
defect would be wrong — so this module labels it INFO/structural and recommends a
scoped filter rather than a repair.
"""
from __future__ import annotations

from atlas.connectors.base import Connector, TableRef, TableSchema
from atlas.quality.modules.base import (
    BusinessImpact, Issue, Repair, RepairModule, col_stats, register,
)
from atlas.quality.rules_loader import module_config


@register
class NullClassification(RepairModule):
    id = "null_classification"
    dimension = "completeness"

    def detect(self, con: Connector, table: TableRef, schema: TableSchema) -> list[Issue]:
        tname = table.qualified()
        thresh = float(module_config(self.id).get("structural_null_rate", 0.90))
        issues: list[Issue] = []
        for c in schema.columns:
            st = col_stats(con, tname, c.name)
            if st["n"] and st["null_rate"] >= thresh and st["non_null"] > 0:
                issues.append(Issue(
                    module_id=self.id, dimension=self.dimension, column=c.name,
                    severity="INFO", confidence=1.0, structural=True,
                    description=(f"'{c.name}' is {st['null_rate']:.0%} NULL — classified structural "
                                f"(populated for a sub-population; not a defect)."),
                    detail={"null_rate": round(st["null_rate"], 4),
                            "populated": int(st["non_null"])},
                ))
        return issues

    def plan(self, con, table, schema, issue) -> Repair | None:
        col = issue.column
        bi = BusinessImpact(
            problem=f"{col} is mostly NULL",
            business_risk="Treating these NULLs as missing data would distort completeness scoring.",
            impact="LOW",
            recommendation=f"Filter to non-NULL {col} when analysing it; do not impute.",
            confidence=1.0,
        )
        # Structural: no clean column, no transformation — an annotation only.
        return Repair(
            module_id=self.id, column=col, clean_column=None,
            sql_expression=None, pandas_code=None,
            confidence=1.0, business_impact=bi, rows_affected=0, row_level=False,
            rollback="No transformation applied (annotation only).",
            notes="Structural null — recorded for scoring/guardrails, not repaired.",
        )
