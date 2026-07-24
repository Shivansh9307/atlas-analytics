"""BigQuery adapter — DORMANT (Phase 7). Prefer Google's BigQuery MCP toolbox;
google-cloud-bigquery is the fallback.

Skeleton only. NOTE: BigQuery is billed by BYTES SCANNED, so estimate_bytes()
(via a dry-run job) MUST be implemented before any wide query runs — that is what
the scan-budget gate reads. Until then, this adapter stays dormant.
"""
from __future__ import annotations

from typing import Any

from atlas.connectors.base import ConnCheck, Connector, TableRef, TableSchema
from atlas.lib.query_store import QueryStore


class BigQueryConnector(Connector):
    dialect = "bigquery"

    def __init__(self, name: str, raw: dict, store: QueryStore | None = None):
        super().__init__(name, store)
        self.raw = raw

    def test_connection(self) -> ConnCheck:
        return ConnCheck(False, "BigQuery adapter is a Phase-7 skeleton; wire the MCP "
                                "toolbox or google-cloud-bigquery, and implement dry-run "
                                "estimate_bytes() before enabling.")

    def list_tables(self, schema: str | None = None) -> list[TableRef]:
        raise NotImplementedError("Phase 7: BigQuery adapter not yet implemented")

    def get_schema(self, table: TableRef) -> TableSchema:
        raise NotImplementedError("Phase 7: BigQuery adapter not yet implemented")

    def estimate_bytes(self, sql: str) -> int | None:
        # Implement via a dry-run job: job_config.dry_run=True -> total_bytes_processed.
        raise NotImplementedError("Phase 7: implement BigQuery dry-run byte estimate")

    def _execute(self, sql: str) -> tuple[list[dict[str, Any]], list[str], int | None]:
        raise NotImplementedError("Phase 7: BigQuery adapter not yet implemented")
