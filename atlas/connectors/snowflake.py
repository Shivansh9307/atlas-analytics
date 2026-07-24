"""Snowflake adapter — DORMANT (Phase 7). Prefer the official Snowflake MCP server;
this driver path (snowflake-connector-python) is the documented fallback.

Skeleton only: fill in once a live account + read-only role/warehouse exist. The
interface and read-only guarantees mirror the Postgres adapter.
"""
from __future__ import annotations

from typing import Any

from atlas.connectors.base import ConnCheck, Connector, TableRef, TableSchema
from atlas.lib.query_store import QueryStore


class SnowflakeConnector(Connector):
    dialect = "snowflake"

    def __init__(self, name: str, raw: dict, store: QueryStore | None = None):
        super().__init__(name, store)
        self.raw = raw

    def test_connection(self) -> ConnCheck:
        return ConnCheck(False, "Snowflake adapter is a Phase-7 skeleton; wire the "
                                "official MCP server or snowflake-connector-python.")

    def list_tables(self, schema: str | None = None) -> list[TableRef]:
        raise NotImplementedError("Phase 7: Snowflake adapter not yet implemented")

    def get_schema(self, table: TableRef) -> TableSchema:
        raise NotImplementedError("Phase 7: Snowflake adapter not yet implemented")

    def estimate_bytes(self, sql: str) -> int | None:
        # Snowflake: use EXPLAIN / query profile for a bytes estimate when implemented.
        return None

    def _execute(self, sql: str) -> tuple[list[dict[str, Any]], list[str], int | None]:
        raise NotImplementedError("Phase 7: Snowflake adapter not yet implemented")
