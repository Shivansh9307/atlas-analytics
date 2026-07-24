"""Month Repair: a precomputed Month column that disagrees with the actual date.

Targets the Sales defect where the denormalised Month label does not reconcile
with Order_Date. Month_Clean is derived from the date so period grain is honest.
"""
from __future__ import annotations

from atlas.connectors.base import Connector, TableRef, TableSchema
from atlas.quality.modules.base import BusinessImpact, Issue, Repair, RepairModule, q, register
from atlas.quality.modules._shared import date_expr, find_column, find_date_column, mismatch_count


@register
class MonthRepair(RepairModule):
    id = "month_repair"
    dimension = "consistency"
    _stored = ("month",)
    _label = "Month"
    # Certainty that the date-derived value is the correct one. Quarter lowers
    # this because a fiscal-vs-calendar quarter definition is genuinely ambiguous
    # (so its repair must be human-approved, never auto-applied).
    _confidence = 0.98

    def _derived(self, dexpr: str) -> str:
        return f"strftime({dexpr}, '%b')"

    def _pandas_derived(self, date_col: str) -> str:
        return f"pd.to_datetime(df[{date_col!r}], errors='coerce').dt.strftime('%b')"

    def detect(self, con: Connector, table: TableRef, schema: TableSchema) -> list[Issue]:
        stored = find_column(schema, *self._stored)
        dc = find_date_column(con, table.qualified(), schema)
        if not stored or not dc:
            return []
        dexpr = date_expr(dc[0], dc[1])
        mism, both = mismatch_count(con, table.qualified(), self._derived(dexpr), stored)
        if both == 0 or mism == 0:
            return []
        rate = mism / both
        return [Issue(
            module_id=self.id, dimension=self.dimension, column=stored,
            severity="HIGH" if rate > 0.05 else "MED", confidence=self._confidence,
            description=(f"'{stored}' disagrees with the date in {mism} of {both} row(s) "
                        f"({rate:.0%}); the precomputed {self._label} label is unreliable."),
            detail={"mismatch": int(mism), "both": int(both), "mismatch_rate": round(rate, 4),
                    "date_col": dc[0], "needs_cast": dc[1]},
        )]

    def plan(self, con, table, schema, issue) -> Repair | None:
        stored = issue.column
        dexpr = date_expr(issue.detail["date_col"], issue.detail["needs_cast"])
        clean = f"{stored}_Clean"
        bi = BusinessImpact(
            problem=f"{stored} does not match the underlying date",
            business_risk=f"{self._label}-grain aggregations bucket rows into the wrong period.",
            impact="HIGH",
            recommendation=f"Derive {clean} from the date column, ignore the stored {stored}.",
            confidence=issue.confidence,
        )
        return Repair(
            module_id=self.id, column=stored, clean_column=clean,
            sql_expression=f"{self._derived(dexpr)} AS {q(clean)}",
            pandas_code=f"df[{clean!r}] = {self._pandas_derived(issue.detail['date_col'])}",
            confidence=issue.confidence, business_impact=bi,
            rows_affected=int(issue.detail["mismatch"]),
            rollback=f"Drop derived column {clean} (raw {stored} untouched).",
        )
