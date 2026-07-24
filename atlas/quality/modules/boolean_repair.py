"""Boolean Repair: yes/no, Y/N, 0/1, true/false text -> a typed BOOLEAN column."""
from __future__ import annotations

from atlas.connectors.base import Connector, TableRef, TableSchema
from atlas.quality.modules.base import (
    BusinessImpact, Issue, Repair, RepairModule, is_text, lit, q, register,
)

TRUE_TOKENS = {"true", "t", "yes", "y", "1"}
FALSE_TOKENS = {"false", "f", "no", "n", "0"}
BOOL_TOKENS = TRUE_TOKENS | FALSE_TOKENS


def _bool_case(col: str) -> str:
    trues = ", ".join(lit(t) for t in sorted(TRUE_TOKENS))
    falses = ", ".join(lit(t) for t in sorted(FALSE_TOKENS))
    return (f"CASE WHEN lower(trim({q(col)})) IN ({trues}) THEN TRUE "
            f"WHEN lower(trim({q(col)})) IN ({falses}) THEN FALSE ELSE NULL END")


@register
class BooleanRepair(RepairModule):
    id = "boolean_repair"
    dimension = "type_safety"

    def detect(self, con: Connector, table: TableRef, schema: TableSchema) -> list[Issue]:
        tname = table.qualified()
        issues: list[Issue] = []
        for c in schema.columns:
            if not is_text(c.dtype):
                continue
            rows = con.run(
                f"SELECT DISTINCT lower(trim({q(c.name)})) AS v FROM {tname} "
                f"WHERE {q(c.name)} IS NOT NULL"
            ).rows
            vals = {r["v"] for r in rows}
            if vals and vals <= BOOL_TOKENS:
                issues.append(Issue(
                    module_id=self.id, dimension=self.dimension, column=c.name,
                    severity="LOW", confidence=1.0,
                    description=f"'{c.name}' holds boolean-like text {sorted(vals)}; type as BOOLEAN.",
                    detail={"values": sorted(vals)},
                ))
        return issues

    def plan(self, con, table, schema, issue) -> Repair | None:
        col = issue.column
        clean = f"{col}_Clean"
        n = con.run(f"SELECT count({q(col)}) AS nn FROM {table.qualified()}").rows[0]["nn"] or 0
        bi = BusinessImpact(
            problem=f"{col} is boolean data stored as text",
            business_risk="Filters and rates on the flag are error-prone.",
            impact="LOW",
            recommendation=f"Add typed {clean} BOOLEAN.",
            confidence=1.0,
        )
        return Repair(
            module_id=self.id, column=col, clean_column=clean,
            sql_expression=f"{_bool_case(col)} AS {q(clean)}",
            pandas_code=(f"df[{clean!r}] = df[{col!r}].str.strip().str.lower().map("
                        f"lambda v: True if v in {sorted(TRUE_TOKENS)} else "
                        f"(False if v in {sorted(FALSE_TOKENS)} else None))"),
            confidence=1.0, business_impact=bi, rows_affected=int(n),
            rollback=f"Drop derived column {clean} (raw {col} untouched).",
        )
