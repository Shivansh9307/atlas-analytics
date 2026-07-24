"""SQL Repair Engine: build the semantic-clean SELECT / CREATE VIEW.

The local (DuckDB) SELECT is executed to materialise the clean view; the same
plan is emitted as CREATE VIEW DDL for warehouse dialects so an operator can
apply it in their own governed schema (Atlas never runs DDL against a source).
"""
from __future__ import annotations

from atlas.quality.modules.base import Transform  # noqa: F401  (type import)

# Dialects we can emit governed DDL for (spec "SQL Repair Engine").
DIALECTS = ["duckdb", "snowflake", "postgres", "bigquery", "databricks", "fabric", "sqlserver"]


def build_clean_select(base_table: str, transforms: list, *, dedup: bool) -> str:
    """SELECT that yields the clean layer: all base columns + derived *_Clean columns.

    `transforms` are the enabled, column-producing repairs (each exposes
    `sql_expression`, already aliased to its clean column). `dedup` adds DISTINCT
    for a row-level duplicate repair.
    """
    exprs = [t.sql_expression for t in transforms if t.sql_expression]
    select_list = ", ".join(["*", *exprs]) if exprs else "*"
    distinct = "DISTINCT " if dedup else ""
    return f"SELECT {distinct}{select_list} FROM {_q(base_table)}"


def build_ddl(clean_table: str, base_table: str, transforms: list, *, dedup: bool,
              dialect: str = "duckdb") -> str:
    """CREATE VIEW DDL for `dialect`. DuckDB uses CREATE OR REPLACE; others a
    portable CREATE VIEW an operator applies in their governed schema."""
    select = build_clean_select(base_table, transforms, dedup=dedup)
    if dialect == "duckdb":
        return f"CREATE OR REPLACE VIEW {_q(clean_table)} AS\n{select};"
    return f"CREATE VIEW {_q(clean_table)} AS\n{select};"


def emit_all_dialects(clean_table: str, base_table: str, transforms: list, *, dedup: bool) -> dict[str, str]:
    """DDL per supported dialect (for the warehouse 'emit, don't run' path)."""
    return {d: build_ddl(clean_table, base_table, transforms, dedup=dedup, dialect=d)
            for d in DIALECTS}


def _q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'
