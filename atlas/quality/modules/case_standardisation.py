"""Case Standardisation: case-variant duplicates of a category -> one canonical case.

Fires only when case-folding actually COLLAPSES distinct values (e.g. 'USA' and
'usa' co-exist), so uniform columns are never touched.
"""
from __future__ import annotations

from atlas.connectors.base import Connector, TableRef, TableSchema
from atlas.quality.modules.base import (
    BusinessImpact, Issue, Repair, RepairModule, is_text, q, register,
)
from atlas.quality.rules_loader import module_config


@register
class CaseStandardisation(RepairModule):
    id = "case_standardisation"
    dimension = "consistency"

    def detect(self, con: Connector, table: TableRef, schema: TableSchema) -> list[Issue]:
        tname = table.qualified()
        floor = int(module_config(self.id).get("min_distinct_collapse", 1))
        issues: list[Issue] = []
        for c in schema.columns:
            if not is_text(c.dtype):
                continue
            r = con.run(
                f"SELECT count(DISTINCT {q(c.name)}) AS d, "
                f"count(DISTINCT lower(trim({q(c.name)}))) AS dl FROM {tname}"
            ).rows[0]
            d = r["d"] or 0
            dl = r["dl"] or 0
            collapse = d - dl
            if collapse >= floor and collapse > 0:
                issues.append(Issue(
                    module_id=self.id, dimension=self.dimension, column=c.name,
                    severity="LOW", confidence=1.0,
                    description=(f"'{c.name}' has {collapse} case-variant duplicate label(s) "
                                f"({d} distinct collapse to {dl}); categories split."),
                    detail={"collapse": int(collapse)},
                ))
        return issues

    def plan(self, con, table, schema, issue) -> Repair | None:
        col = issue.column
        clean = f"{col}_Clean"
        bi = BusinessImpact(
            problem=f"{col} mixes letter case for the same category",
            business_risk="One category appears as several, fragmenting every breakdown.",
            impact="LOW",
            recommendation=f"Normalise into {clean} = upper(trim({col})).",
            confidence=1.0,
        )
        return Repair(
            module_id=self.id, column=col, clean_column=clean,
            sql_expression=f"upper(trim({q(col)})) AS {q(clean)}",
            pandas_code=f"df[{clean!r}] = df[{col!r}].str.strip().str.upper()",
            confidence=1.0, business_impact=bi, rows_affected=int(issue.detail["collapse"]),
            rollback=f"Drop derived column {clean} (raw {col} untouched).",
            notes="Canonical case is upper(); adjust in a future rule if a display case is needed.",
        )
