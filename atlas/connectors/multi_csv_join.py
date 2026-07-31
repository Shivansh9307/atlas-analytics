"""Joins several CSVs into one analytical view within a single DuckDB connection.

CsvDuckDBConnector gives every source its own private `:memory:` engine, which
is right for provenance isolation but means no `run()` can query across two
registered sources — there is structurally no way to JOIN `fact_returns_csv`
against `dim_products_csv`, say, because they never share a connection.

This connector is the escape hatch: it opens ONE connection, registers each
declared source file as a view inside it, then builds a single `table_name`
view over them via operator-declared `view_sql` (sources.yaml `join.view_sql`)
— a declared join, never a guessed one, same spirit as `derived_columns`.

CSV/TSV only (no Excel, no non-UTF-8 fallback): nothing this connector joins
today needs either. Extend `_register_source` if a future joined source does.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from atlas.connectors.base import (
    ColumnSchema,
    ConnCheck,
    Connector,
    TableRef,
    TableSchema,
)
from atlas.connectors.csv_duckdb import _q_ident, _sql_literal
from atlas.lib.query_store import QueryStore


class MultiCsvJoinConnector(Connector):
    dialect = "duckdb"

    def __init__(
        self,
        name: str,
        *,
        sources: dict[str, str],
        view_sql: str,
        table_name: str,
        store: QueryStore | None = None,
        row_limit: int | None = None,
        extra_views: dict[str, str] | None = None,
    ):
        """`extra_views`: additional named views built after the main one, e.g. a
        per-target modeling view that EXCLUDEs sibling/leakage-adjacent columns
        the generic column-binding layer has no domain knowledge to drop itself
        (binding only ever excludes the bound target + entity, nothing else)."""
        super().__init__(name, store)
        self.table_name = table_name
        self.row_limit = row_limit
        self.warnings: list[str] = []
        self._con = duckdb.connect(database=":memory:")
        for alias, path in sources.items():
            self._register_source(alias, Path(path))
        self._con.execute(f"CREATE VIEW {_q_ident(self.table_name)} AS {view_sql}")
        for view_name, sql in (extra_views or {}).items():
            self._con.execute(f"CREATE VIEW {_q_ident(view_name)} AS {sql}")

    def _register_source(self, alias: str, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"source file not found: {path}")
        suffix = path.suffix.lower()
        if suffix not in (".csv", ".tsv"):
            raise ValueError(
                f"MultiCsvJoinConnector only supports csv/tsv today: {path} "
                f"(alias '{alias}')"
            )
        sep = "\t" if suffix == ".tsv" else ","
        lit = _sql_literal(str(path))
        self._con.execute(
            f"CREATE VIEW {_q_ident(alias)} AS SELECT * FROM "
            f"read_csv_auto({lit}, sep={_sql_literal(sep)}, header=true)"
        )

    # ---- semantic clean layer / model output (same contract as CsvDuckDBConnector) ---
    def materialize_clean(self, clean_table: str, select_sql: str) -> None:
        """Create (or replace) a derived clean VIEW in the LOCAL engine.

        Same read-only-to-source-safe write path as `CsvDuckDBConnector`: this
        connector also owns its own private in-memory DuckDB engine, so it can
        materialise a clean view directly rather than falling back to the
        warehouse DDL-emission path. Never called through `run()`.
        """
        self._con.execute(f"CREATE OR REPLACE VIEW {_q_ident(clean_table)} AS {select_sql}")

    def drop_clean(self, clean_table: str) -> None:
        self._con.execute(f"DROP VIEW IF EXISTS {_q_ident(clean_table)}")

    def materialize_scores(self, table_name: str, rows: list[dict]) -> None:
        """Register model output as a LOCAL DuckDB view. Never a write to the source."""
        if not rows:
            raise ValueError("materialize_scores() needs at least one row")
        import pandas as pd
        df = pd.DataFrame(rows)
        self._con.register(f"_{table_name}_df", df)
        self._con.execute(
            f"CREATE OR REPLACE VIEW {_q_ident(table_name)} AS "
            f"SELECT * FROM _{table_name}_df"
        )

    def has_table(self, name: str) -> bool:
        row = self._con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
        ).fetchone()
        return bool(row and row[0])

    # ---- Connector interface ----
    def test_connection(self) -> ConnCheck:
        try:
            n = self._con.execute(
                f"SELECT count(*) FROM {_q_ident(self.table_name)}"
            ).fetchone()[0]
            return ConnCheck(
                ok=True, detail=f"joined view {self.table_name} ({n} rows)",
                read_only_role=True, latency_ms=0.0,
            )
        except Exception as e:  # pragma: no cover
            return ConnCheck(ok=False, detail=str(e))

    def list_tables(self, schema: str | None = None) -> list[TableRef]:
        return [TableRef(name=self.table_name)]

    def get_schema(self, table: TableRef) -> TableSchema:
        rows = self._con.execute(f"DESCRIBE {table.name}").fetchall()
        cols = [
            ColumnSchema(name=r[0], dtype=str(r[1]), nullable=(str(r[2]).upper() != "NO"))
            for r in rows
        ]
        return TableSchema(table=table, columns=cols)

    def estimate_bytes(self, sql: str) -> int | None:
        return None

    def _execute(self, sql: str) -> tuple[list[dict[str, Any]], list[str], int | None]:
        cur = self._con.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        fetched = cur.fetchall()
        if self.row_limit is not None and len(fetched) > self.row_limit:
            fetched = fetched[: self.row_limit]
        rows = [dict(zip(columns, r)) for r in fetched]
        return rows, columns, None

    def close(self) -> None:
        try:
            self._con.close()
        except Exception:
            pass
