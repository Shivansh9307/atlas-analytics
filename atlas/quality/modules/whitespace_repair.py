"""Whitespace Repair: leading/trailing whitespace in text -> a trimmed column."""
from __future__ import annotations

from atlas.connectors.base import Connector, TableRef, TableSchema
from atlas.quality.modules.base import (
    BusinessImpact, Issue, Repair, RepairModule, is_text, q, register,
)


@register
class WhitespaceRepair(RepairModule):
    id = "whitespace_repair"
    dimension = "consistency"

    def detect(self, con: Connector, table: TableRef, schema: TableSchema) -> list[Issue]:
        tname = table.qualified()
        issues: list[Issue] = []
        for c in schema.columns:
            if not is_text(c.dtype):
                continue
            bad = con.run(
                f"SELECT count(*) AS c FROM {tname} "
                f"WHERE {q(c.name)} IS NOT NULL AND {q(c.name)} <> trim({q(c.name)})"
            ).rows[0]["c"] or 0
            if bad:
                issues.append(Issue(
                    module_id=self.id, dimension=self.dimension, column=c.name,
                    severity="LOW", confidence=1.0,
                    description=f"'{c.name}' has {bad} value(s) with stray whitespace; grouping splits.",
                    detail={"affected": int(bad)},
                ))
        return issues

    def plan(self, con, table, schema, issue) -> Repair | None:
        col = issue.column
        clean = f"{col}_Clean"
        bi = BusinessImpact(
            problem=f"{col} has untrimmed values",
            business_risk="'Value' and 'Value ' group separately, fragmenting rollups.",
            impact="LOW",
            recommendation=f"Add trimmed {clean} = trim({col}).",
            confidence=1.0,
        )
        return Repair(
            module_id=self.id, column=col, clean_column=clean,
            sql_expression=f"trim({q(col)}) AS {q(clean)}",
            pandas_code=f"df[{clean!r}] = df[{col!r}].str.strip()",
            confidence=1.0, business_impact=bi, rows_affected=int(issue.detail["affected"]),
            rollback=f"Drop derived column {clean} (raw {col} untouched).",
        )
