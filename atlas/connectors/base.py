"""Uniform connector interface over every data source.

Concrete adapters (csv_duckdb, postgres, snowflake, bigquery, databricks) all
implement Connector. Every read routes through run(), which:
  1. asserts read-only (defence in depth with the PreToolUse hook),
  2. optionally enforces a byte budget,
  3. hashes query + result and persists via QueryStore.

This guarantees provenance is structural, not a courtesy the caller might skip.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from atlas.lib.query_store import QueryResult, QueryStore, hash_query, hash_result
from atlas.lib.sqlguard import assert_read_only


@dataclass
class TableRef:
    name: str
    schema: str | None = None

    def qualified(self) -> str:
        return f"{self.schema}.{self.name}" if self.schema else self.name


@dataclass
class ColumnSchema:
    name: str
    dtype: str
    nullable: bool = True


@dataclass
class TableSchema:
    table: TableRef
    columns: list[ColumnSchema]


@dataclass
class ConnCheck:
    ok: bool
    detail: str = ""
    read_only_role: bool | None = None
    latency_ms: float | None = None


@dataclass
class ProfileReport:
    table: TableRef
    row_count: int
    columns: list[dict[str, Any]] = field(default_factory=list)  # per-col stats
    duplicate_key_candidates: list[list[str]] = field(default_factory=list)
    grain: list[str] | None = None
    freshness: str | None = None
    warnings: list[str] = field(default_factory=list)


class BudgetExceeded(Exception):
    """Raised when a query is projected to exceed the scan-byte budget."""


class Connector(ABC):
    dialect: str = "unknown"

    def __init__(self, name: str, store: QueryStore | None = None):
        import threading
        self.name = name
        self.store = store
        # Serialises execution so parallel DAG nodes can share one connector safely
        # (DuckDB connections are not safe for concurrent queries).
        self._exec_lock = threading.Lock()

    # ---- required capabilities ----
    @abstractmethod
    def test_connection(self) -> ConnCheck: ...

    @abstractmethod
    def list_tables(self, schema: str | None = None) -> list[TableRef]: ...

    @abstractmethod
    def get_schema(self, table: TableRef) -> TableSchema: ...

    @abstractmethod
    def _execute(self, sql: str) -> tuple[list[dict[str, Any]], list[str], int | None]:
        """Adapter-specific execution. Returns (rows, columns, bytes_scanned).

        MUST NOT be called directly by callers — go through run() so that
        read-only enforcement, budgeting, hashing and storage all happen.
        """
        ...

    def estimate_bytes(self, sql: str) -> int | None:
        """Dry-run cost estimate. Default None = unsupported (e.g. local files)."""
        return None

    def profile(self, table: TableRef, sample: int | None = None) -> ProfileReport:
        """Default profiling via SQL; adapters may override for native stats."""
        from atlas.lib.profiling import profile_table
        return profile_table(self, table, sample=sample)

    # ---- the single guarded entry point ----
    def run(
        self,
        sql: str,
        *,
        sample: int | None = None,
        max_bytes: int | None = None,
        purpose: str = "",
    ) -> QueryResult:
        # 1. read-only enforcement (connector layer; hook is the outer layer)
        assert_read_only(sql)

        # 2. byte budget (warehouses only; local returns None and is skipped)
        if max_bytes is not None:
            est = self.estimate_bytes(sql)
            if est is not None and est > max_bytes:
                raise BudgetExceeded(
                    f"query projected to scan {est:,} bytes > budget {max_bytes:,}. "
                    "Confirm explicitly (raise --max-bytes) before running."
                )

        # 3. execute (serialised — parallel DAG nodes may share this connector)
        with self._exec_lock:
            rows, columns, bytes_scanned = self._execute(sql)

        # 4. hash + package
        qh = hash_query(sql, self.name, self.dialect)
        rh = hash_result(rows, columns)
        result = QueryResult(
            rows=rows, columns=columns, query_hash=qh, result_hash=rh,
            source=self.name, dialect=self.dialect, sql=sql,
            bytes_scanned=bytes_scanned, sampled=sample is not None,
        )

        # 5. persist (provenance is structural)
        if self.store is not None:
            self.store.store(result)
        return result

    def close(self) -> None:  # optional override
        pass
