"""Repair-module plugin framework.

Every data-quality repair is a pluggable module implementing the spec's seven
faces: Detector, Repair, Confidence, Business Impact, Transformation (SQL +
pandas), Rollback, Audit. Modules self-register via the @register decorator, so
new modules (and, later, whole copilots) plug in without touching core code.

Detection routes every probe through `Connector.run()` (read-only, provenance-
stamped). A module NEVER mutates the source — it only proposes a derived
`<col>_Clean` column (or a row-level flag) that the clean-layer builder
materialises as a DuckDB view in the local engine.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from atlas.connectors.base import Connector, TableRef, TableSchema

# Severity ordering for ranking / gating.
SEVERITY_RANK = {"HIGH": 3, "MED": 2, "LOW": 1, "INFO": 0}


@dataclass
class BusinessImpact:
    """The Business Impact Engine payload attached to every issue/repair."""
    problem: str
    business_risk: str          # e.g. "North America excluded if Region filter used"
    impact: str                 # HIGH | MED | LOW  (business-facing)
    recommendation: str
    confidence: float           # 0..1

    def as_dict(self) -> dict:
        return {
            "problem": self.problem,
            "business_risk": self.business_risk,
            "impact": self.impact,
            "recommendation": self.recommendation,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class Issue:
    """A detected data-quality defect (or a structural, by-design observation)."""
    module_id: str
    dimension: str              # completeness/validity/consistency/type_safety/...
    column: str | None
    severity: str               # HIGH | MED | LOW | INFO
    description: str
    confidence: float
    structural: bool = False    # True => by-design (not a defect), e.g. churn_reason nulls
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "module_id": self.module_id,
            "dimension": self.dimension,
            "column": self.column,
            "severity": self.severity,
            "description": self.description,
            "confidence": round(self.confidence, 4),
            "structural": self.structural,
            "detail": self.detail,
        }


@dataclass
class Repair:
    """A proposed, reversible transformation. SQL is a SELECT-list expression that
    produces `clean_column`; pandas is the equivalent. No source mutation."""
    module_id: str
    column: str | None
    clean_column: str | None            # e.g. "Region_Clean"; None for row-level (dedup)
    sql_expression: str | None          # DuckDB SELECT-list expr aliased to clean_column
    pandas_code: str | None             # e.g. "df['Region_Clean'] = df['Region'].fillna(...)"
    confidence: float
    business_impact: BusinessImpact
    rows_affected: int
    rollback: str                       # human-readable reversal (drop column / drop view)
    row_level: bool = False             # True => affects row set (e.g. DISTINCT), not a column
    notes: str = ""

    def as_dict(self) -> dict:
        return {
            "module_id": self.module_id,
            "column": self.column,
            "clean_column": self.clean_column,
            "sql_expression": self.sql_expression,
            "pandas_code": self.pandas_code,
            "confidence": round(self.confidence, 4),
            "business_impact": self.business_impact.as_dict(),
            "rows_affected": self.rows_affected,
            "rollback": self.rollback,
            "row_level": self.row_level,
            "notes": self.notes,
        }


@dataclass
class Transform:
    """A Repair placed in the transformation pipeline: sequenced, approvable,
    individually enable/disable-able (spec 'Transformation Pipeline')."""
    seq: int
    module_id: str
    column: str | None
    clean_column: str | None
    sql_expression: str | None
    pandas_code: str | None
    confidence: float
    row_level: bool
    rows_affected: int
    rollback: str
    business_impact: dict
    approved_by: str = "auto"          # "auto" | "user"
    enabled: bool = True
    ts: str = ""
    notes: str = ""

    @classmethod
    def from_repair(cls, repair: Repair, seq: int, *, approved_by: str, ts: str) -> "Transform":
        return cls(
            seq=seq, module_id=repair.module_id, column=repair.column,
            clean_column=repair.clean_column, sql_expression=repair.sql_expression,
            pandas_code=repair.pandas_code, confidence=repair.confidence,
            row_level=repair.row_level, rows_affected=repair.rows_affected,
            rollback=repair.rollback, business_impact=repair.business_impact.as_dict(),
            approved_by=approved_by, ts=ts, notes=repair.notes,
        )

    def as_dict(self) -> dict:
        return {
            "seq": self.seq, "module_id": self.module_id, "column": self.column,
            "clean_column": self.clean_column, "sql_expression": self.sql_expression,
            "pandas_code": self.pandas_code, "confidence": round(self.confidence, 4),
            "row_level": self.row_level, "rows_affected": self.rows_affected,
            "rollback": self.rollback, "business_impact": self.business_impact,
            "approved_by": self.approved_by, "enabled": self.enabled,
            "ts": self.ts, "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Transform":
        return cls(
            seq=d["seq"], module_id=d["module_id"], column=d.get("column"),
            clean_column=d.get("clean_column"), sql_expression=d.get("sql_expression"),
            pandas_code=d.get("pandas_code"), confidence=d.get("confidence", 0.0),
            row_level=d.get("row_level", False), rows_affected=d.get("rows_affected", 0),
            rollback=d.get("rollback", ""), business_impact=d.get("business_impact", {}),
            approved_by=d.get("approved_by", "auto"), enabled=d.get("enabled", True),
            ts=d.get("ts", ""), notes=d.get("notes", ""),
        )


class RepairModule(ABC):
    id: str = "base"
    dimension: str = "validity"

    @abstractmethod
    def detect(self, con: Connector, table: TableRef, schema: TableSchema) -> list[Issue]:
        """Return the issues this module finds on `table`. Empty list = nothing to do."""
        ...

    @abstractmethod
    def plan(self, con: Connector, table: TableRef, schema: TableSchema,
             issue: Issue) -> Repair | None:
        """Turn one of this module's issues into a concrete, reversible Repair."""
        ...


# ---- registry ----------------------------------------------------------------
REGISTRY: dict[str, RepairModule] = {}


def register(cls):
    """Class decorator: instantiate and register a RepairModule by its id."""
    inst = cls()
    REGISTRY[inst.id] = inst
    return cls


def all_modules() -> list[RepairModule]:
    """Registered modules, in a stable id order (determinism)."""
    return [REGISTRY[k] for k in sorted(REGISTRY)]


# ---- shared detection helpers (all via guarded run()) ------------------------
def q(ident: str) -> str:
    """Quote a SQL identifier."""
    return '"' + ident.replace('"', '""') + '"'


def lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def col_stats(con: Connector, tname: str, column: str) -> dict:
    """(n, non_null, distinct, null_rate) for one column — one guarded query."""
    r = con.run(
        f"SELECT count(*) AS n, count({q(column)}) AS non_null, "
        f"count(DISTINCT {q(column)}) AS distinct_ct FROM {tname}"
    ).rows[0]
    n = r["n"] or 0
    non_null = r["non_null"] or 0
    distinct = r["distinct_ct"] or 0
    return {
        "n": n,
        "non_null": non_null,
        "distinct": distinct,
        "null_rate": (n - non_null) / n if n else 0.0,
    }


def is_text(dtype: str) -> bool:
    return dtype.upper().startswith(("VARCHAR", "CHAR", "TEXT", "STRING"))


def is_numeric(dtype: str) -> bool:
    u = dtype.upper()
    return u.startswith(("BIGINT", "INT", "DOUBLE", "DECIMAL", "FLOAT", "REAL", "HUGEINT", "NUMERIC"))
