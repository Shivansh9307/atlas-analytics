"""Databricks adapter — DORMANT (Phase 7). Prefer the official Databricks MCP
server; databricks-sql-connector is the fallback.

Skeleton only. Interface and read-only guarantees mirror the Postgres adapter.
"""
from __future__ import annotations

from typing import Any

from atlas.connectors.base import ConnCheck, Connector, TableRef, TableSchema
from atlas.lib.query_store import QueryStore


class DatabricksConnector(Connector):
    dialect = "databricks"

    def __init__(self, name: str, raw: dict, store: QueryStore | None = None):
        super().__init__(name, store)
        self.raw = raw

    def test_connection(self) -> ConnCheck:
        return ConnCheck(False, "Databricks adapter is a Phase-7 skeleton; wire the "
                                "official MCP server or databricks-sql-connector.")

    def list_tables(self, schema: str | None = None) -> list[TableRef]:
        raise NotImplementedError("Phase 7: Databricks adapter not yet implemented")

    def get_schema(self, table: TableRef) -> TableSchema:
        raise NotImplementedError("Phase 7: Databricks adapter not yet implemented")

    def _execute(self, sql: str) -> tuple[list[dict[str, Any]], list[str], int | None]:
        raise NotImplementedError("Phase 7: Databricks adapter not yet implemented")
