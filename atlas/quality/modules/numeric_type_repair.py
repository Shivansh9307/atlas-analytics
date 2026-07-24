"""Numeric Type Repair: numbers stored as text -> a typed numeric column."""
from __future__ import annotations

from atlas.connectors.base import Connector, TableRef, TableSchema
from atlas.quality.modules.base import (
    BusinessImpact, Issue, Repair, RepairModule, is_text, q, register,
)
from atlas.quality.modules._shared import date_parse_rate
from atlas.quality.rules_loader import module_config


@register
class NumericTypeRepair(RepairModule):
    id = "numeric_type_repair"
    dimension = "type_safety"

    def detect(self, con: Connector, table: TableRef, schema: TableSchema) -> list[Issue]:
        tname = table.qualified()
        floor = float(module_config(self.id).get("min_parse_rate", 0.99))
        issues: list[Issue] = []
        for c in schema.columns:
            if not is_text(c.dtype):
                continue
            # Skip columns that are really dates (date_repair owns those).
            if date_parse_rate(con, tname, c.name) >= floor:
                continue
            r = con.run(
                f"SELECT count({q(c.name)}) AS nn, "
                f"count(TRY_CAST({q(c.name)} AS DOUBLE)) AS ok FROM {tname}"
            ).rows[0]
            nn = r["nn"] or 0
            if nn == 0:
                continue
            pr = (r["ok"] or 0) / nn
            if pr >= floor:
                issues.append(Issue(
                    module_id=self.id, dimension=self.dimension, column=c.name,
                    severity="MED", confidence=round(pr, 4),
                    description=(f"'{c.name}' is {c.dtype} but {pr:.0%} parses as numeric; "
                                f"maths/aggregation may sort or error as text."),
                    detail={"parse_rate": round(pr, 4)},
                ))
        return issues

    def plan(self, con, table, schema, issue) -> Repair | None:
        col = issue.column
        clean = f"{col}_Clean"
        n = con.run(f"SELECT count({q(col)}) AS nn FROM {table.qualified()}").rows[0]["nn"] or 0
        bi = BusinessImpact(
            problem=f"{col} stored as text, not a number",
            business_risk="Sorting is lexical and aggregation may fail or mislead.",
            impact="MED",
            recommendation=f"Add typed {clean} = CAST({col} AS DOUBLE).",
            confidence=issue.confidence,
        )
        return Repair(
            module_id=self.id, column=col, clean_column=clean,
            sql_expression=f"TRY_CAST({q(col)} AS DOUBLE) AS {q(clean)}",
            pandas_code=f"df[{clean!r}] = pd.to_numeric(df[{col!r}], errors='coerce')",
            confidence=issue.confidence, business_impact=bi, rows_affected=int(n),
            rollback=f"Drop derived column {clean} (raw {col} untouched).",
        )
