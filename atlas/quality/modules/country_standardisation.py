"""Country Standardisation: messy country spellings -> a canonical label."""
from __future__ import annotations

from atlas.connectors.base import Connector, TableRef, TableSchema
from atlas.quality.modules.base import (
    BusinessImpact, Issue, Repair, RepairModule, lit, q, register,
)
from atlas.quality.modules._shared import find_column
from atlas.quality.rules_loader import country_standardisation


def _std_case(col: str) -> str:
    mapping = country_standardisation()
    whens = "\n".join(
        f"    WHEN lower(trim({q(col)})) = {lit(k)} THEN {lit(v)}"
        for k, v in sorted(mapping.items())
    )
    return f"CASE\n{whens}\n    ELSE {q(col)}\n  END"


@register
class CountryStandardisation(RepairModule):
    id = "country_standardisation"
    dimension = "consistency"

    def detect(self, con: Connector, table: TableRef, schema: TableSchema) -> list[Issue]:
        col = find_column(schema, "country")
        if not col:
            return []
        # Count rows whose canonicalised value differs from the stored value.
        case_expr = _std_case(col)
        changed = con.run(
            f"SELECT count(*) AS c FROM {table.qualified()} "
            f"WHERE {q(col)} IS NOT NULL AND ({case_expr}) <> {q(col)}"
        ).rows[0]["c"] or 0
        if changed == 0:
            return []
        return [Issue(
            module_id=self.id, dimension=self.dimension, column=col,
            severity="MED", confidence=1.0,
            description=f"'{col}' has {changed} non-canonical spelling(s); joins/grouping split.",
            detail={"changed": int(changed)},
        )]

    def plan(self, con, table, schema, issue) -> Repair | None:
        col = issue.column
        clean = f"{col}_Clean"
        bi = BusinessImpact(
            problem=f"{col} spellings are inconsistent",
            business_risk="The same country groups as several, fragmenting every geo rollup.",
            impact="MED",
            recommendation=f"Standardise into {clean} via the canonical mapping.",
            confidence=1.0,
        )
        return Repair(
            module_id=self.id, column=col, clean_column=clean,
            sql_expression=f"{_std_case(col)} AS {q(clean)}",
            pandas_code=(f"df[{clean!r}] = df[{col!r}].where(~df[{col!r}].notna(), "
                        f"df[{col!r}].str.strip().str.lower().map(CANONICAL).fillna(df[{col!r}]))"),
            confidence=1.0, business_impact=bi, rows_affected=int(issue.detail["changed"]),
            rollback=f"Drop derived column {clean} (raw {col} untouched).",
            notes="Mapping is config-driven (rules/country_standardisation.yaml).",
        )
