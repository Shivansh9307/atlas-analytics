"""CSV / Excel connector backed by a local DuckDB engine.

This is the LIVE adapter (no credentials needed). Files are registered as DuckDB
views so the sql-engineer writes ordinary SQL against them. Excel is normalised
via openpyxl->pandas first (handles multi-sheet; flags merged/ambiguous headers).
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
from atlas.lib.query_store import QueryStore


class CsvDuckDBConnector(Connector):
    dialect = "duckdb"

    def __init__(
        self,
        name: str,
        path: str | Path,
        *,
        table_name: str | None = None,
        sheet: str | int | None = None,
        store: QueryStore | None = None,
        row_limit: int | None = None,
    ):
        super().__init__(name, store)
        self.path = Path(path)
        self.table_name = table_name or _safe_ident(self.path.stem)
        self.sheet = sheet
        self.row_limit = row_limit
        self.warnings: list[str] = []
        self._con = duckdb.connect(database=":memory:")
        self._register()

    # ---- registration ----
    def _register(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"source file not found: {self.path}")
        suffix = self.path.suffix.lower()
        # CREATE VIEW cannot be prepared in DuckDB; inline a safely-escaped path.
        # The path comes from sources.yaml (operator-controlled), never user SQL.
        lit = _sql_literal(str(self.path))
        if suffix in (".csv", ".tsv"):
            sep = "\t" if suffix == ".tsv" else ","
            self._con.execute(
                f"CREATE VIEW {self.table_name} AS SELECT * FROM "
                f"read_csv_auto({lit}, sep={_sql_literal(sep)}, header=true)"
            )
        elif suffix in (".xlsx", ".xls"):
            self._register_excel()
        elif suffix == ".parquet":
            self._con.execute(
                f"CREATE VIEW {self.table_name} AS SELECT * FROM read_parquet({lit})"
            )
        else:
            raise ValueError(f"unsupported file type: {suffix}")

    def _register_excel(self) -> None:
        """Normalise Excel (the usual mess) into a clean DuckDB table."""
        import pandas as pd

        xls = pd.ExcelFile(self.path)
        sheet = self.sheet if self.sheet is not None else xls.sheet_names[0]
        if len(xls.sheet_names) > 1 and self.sheet is None:
            self.warnings.append(
                f"workbook has {len(xls.sheet_names)} sheets; defaulted to "
                f"'{sheet}'. Specify sheet= to pick another."
            )
        df = xls.parse(sheet)
        # detect merged/blank header artefacts
        unnamed = [c for c in df.columns if str(c).startswith("Unnamed")]
        if unnamed:
            self.warnings.append(
                f"{len(unnamed)} unnamed/merged header column(s) detected on sheet "
                f"'{sheet}' — header grain may be ambiguous."
            )
        df = df.dropna(how="all")  # drop phantom all-empty rows
        self._con.register(f"_{self.table_name}_df", df)
        self._con.execute(
            f"CREATE VIEW {self.table_name} AS SELECT * FROM _{self.table_name}_df"
        )

    # ---- semantic clean layer -------------------------------------------
    def materialize_clean(self, clean_table: str, select_sql: str) -> None:
        """Create (or replace) a derived clean VIEW in the LOCAL engine.

        This is the read-only-to-source-safe write path for the semantic clean
        layer: it issues CREATE VIEW directly on the in-memory DuckDB engine —
        exactly as `_register()` does for the source view — and NEVER through
        `run()`, so the source guard on CREATE stays fully intact. The source
        file is only ever read; the clean layer lives only in local DuckDB.
        `select_sql` is operator/module-controlled (built from repair plans and
        the config mappings), never raw user SQL.
        """
        self._con.execute(f"CREATE OR REPLACE VIEW {_q_ident(clean_table)} AS {select_sql}")

    def drop_clean(self, clean_table: str) -> None:
        self._con.execute(f"DROP VIEW IF EXISTS {_q_ident(clean_table)}")

    def has_table(self, name: str) -> bool:
        row = self._con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
        ).fetchone()
        return bool(row and row[0])

    # ---- Connector interface ----
    def test_connection(self) -> ConnCheck:
        try:
            n = self._con.execute(
                f"SELECT count(*) FROM {self.table_name}"
            ).fetchone()[0]
            detail = f"{self.path.name} -> view {self.table_name} ({n} rows)"
            if self.warnings:
                detail += " | warnings: " + "; ".join(self.warnings)
            return ConnCheck(ok=True, detail=detail, read_only_role=True, latency_ms=0.0)
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
        # Local files: no warehouse cost. Return None so budgeting is skipped.
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


def _sql_literal(value: str) -> str:
    """Single-quoted SQL string literal with quotes escaped."""
    return "'" + value.replace("'", "''") + "'"


def _q_ident(ident: str) -> str:
    """Double-quoted SQL identifier with embedded quotes escaped."""
    return '"' + ident.replace('"', '""') + '"'


def _safe_ident(stem: str) -> str:
    import re
    ident = re.sub(r"[^0-9A-Za-z_]", "_", stem)
    if ident and ident[0].isdigit():
        ident = "t_" + ident
    return ident or "src"
