"""Date Repair: a text column that is really a date -> a typed DATE column."""
from __future__ import annotations

from atlas.connectors.base import Connector, TableRef, TableSchema
from atlas.quality.modules.base import (
    BusinessImpact, Issue, Repair, RepairModule, is_text, q, register,
)
from atlas.quality.modules._shared import date_parse_rate
from atlas.quality.rules_loader import module_config


@register
class DateRepair(RepairModule):
    id = "date_repair"
    dimension = "type_safety"

    def detect(self, con: Connector, table: TableRef, schema: TableSchema) -> list[Issue]:
        tname = table.qualified()
        floor = float(module_config(self.id).get("min_parse_rate", 0.99))
        issues: list[Issue] = []
        for c in schema.columns:
            if not is_text(c.dtype):
                continue
            # Only text columns that look like dates (name hint or high parse rate).
            pr = date_parse_rate(con, tname, c.name)
            looks_dateish = "date" in c.name.lower() or pr >= floor
            if pr >= floor and looks_dateish:
                issues.append(Issue(
                    module_id=self.id, dimension=self.dimension, column=c.name,
                    severity="HIGH", confidence=round(pr, 4),
                    description=(f"'{c.name}' is stored as {c.dtype} but {pr:.0%} of values "
                                f"parse cleanly as DATE — time intelligence is unreliable."),
                    detail={"parse_rate": round(pr, 4), "dtype": c.dtype},
                ))
        return issues

    def plan(self, con, table, schema, issue) -> Repair | None:
        col = issue.column
        clean = f"{col}_Clean"
        n = con.run(f"SELECT count({q(col)}) AS nn FROM {table.qualified()}").rows[0]["nn"] or 0
        bi = BusinessImpact(
            problem=f"{col} stored as text, not DATE",
            business_risk="Time-series, trend, and freshness analysis are unreliable or impossible.",
            impact="HIGH",
            recommendation=f"Add typed {clean} = CAST({col} AS DATE); analytics reads {clean}.",
            confidence=issue.confidence,
        )
        return Repair(
            module_id=self.id, column=col, clean_column=clean,
            sql_expression=f"TRY_CAST({q(col)} AS DATE) AS {q(clean)}",
            pandas_code=f"df[{clean!r}] = pd.to_datetime(df[{col!r}], errors='coerce').dt.date",
            confidence=issue.confidence, business_impact=bi, rows_affected=int(n),
            rollback=f"Drop derived column {clean} (raw {col} untouched).",
            notes="TRY_CAST leaves unparseable values NULL rather than failing.",
        )
