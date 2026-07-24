"""Region Repair: fill a NULL/partial Region from Country via a config mapping.

Targets the classic Sales defect: Region is only ever APAC/EMEA and is NULL for
every USA/Canada row, so any `WHERE Region IS NOT NULL` silently drops North
America. Region_Clean = COALESCE(Region, map(Country)).
"""
from __future__ import annotations

from atlas.connectors.base import Connector, TableRef, TableSchema
from atlas.quality.modules.base import (
    BusinessImpact, Issue, Repair, RepairModule, lit, q, register,
)
from atlas.quality.modules._shared import find_column
from atlas.quality.rules_loader import country_region_mapping


def _region_case(country_col: str) -> str:
    """Build a CASE expression mapping Country -> canonical Region from config."""
    mapping = country_region_mapping()["country_to_region"]
    whens = "\n".join(
        f"    WHEN lower(trim({q(country_col)})) = {lit(k)} THEN {lit(v)}"
        for k, v in sorted(mapping.items())
    )
    return f"CASE\n{whens}\n    ELSE NULL\n  END"


@register
class RegionRepair(RepairModule):
    id = "region_repair"
    dimension = "completeness"

    def detect(self, con: Connector, table: TableRef, schema: TableSchema) -> list[Issue]:
        tname = table.qualified()
        region_col = find_column(schema, "region")
        country_col = find_column(schema, "country")
        if not region_col or not country_col:
            return []
        r = con.run(
            f"SELECT count(*) AS n, "
            f"count({q(region_col)}) AS non_null FROM {tname}"
        ).rows[0]
        n = r["n"] or 0
        nulls = n - (r["non_null"] or 0)
        if n == 0 or nulls == 0:
            return []
        # How many of those nulls can we actually recover from Country?
        case_expr = _region_case(country_col)
        rec = con.run(
            f"SELECT count(*) AS recoverable FROM {tname} "
            f"WHERE {q(region_col)} IS NULL AND ({case_expr}) IS NOT NULL"
        ).rows[0]["recoverable"] or 0
        conf = rec / nulls if nulls else 0.0
        return [Issue(
            module_id=self.id, dimension=self.dimension, column=region_col,
            severity="HIGH", confidence=round(conf, 4),
            description=(f"'{region_col}' is NULL for {nulls} row(s) ({nulls / n:.0%}); "
                        f"{rec} recoverable from '{country_col}'."),
            detail={"null_rows": int(nulls), "recoverable": int(rec),
                    "country_col": country_col},
        )]

    def plan(self, con, table, schema, issue) -> Repair | None:
        region_col = issue.column
        country_col = issue.detail["country_col"]
        clean = f"{region_col}_Clean"
        case_expr = _region_case(country_col)
        bi = BusinessImpact(
            problem=f"{region_col} missing for a whole geography",
            business_risk="North America excluded whenever a Region filter is applied.",
            impact="HIGH",
            recommendation=f"Derive {clean} = COALESCE({region_col}, map({country_col})).",
            confidence=issue.confidence,
        )
        return Repair(
            module_id=self.id, column=region_col, clean_column=clean,
            sql_expression=f"COALESCE({q(region_col)}, {case_expr}) AS {q(clean)}",
            pandas_code=(f"df[{clean!r}] = df[{region_col!r}].fillna("
                        f"df[{country_col!r}].str.strip().str.lower().map(COUNTRY_TO_REGION))"),
            confidence=issue.confidence, business_impact=bi,
            rows_affected=int(issue.detail["recoverable"]),
            rollback=f"Drop derived column {clean} (raw {region_col} untouched).",
            notes=f"Mapping is config-driven (rules/country_region_mapping.yaml).",
        )
