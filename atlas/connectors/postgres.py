"""Postgres adapter (DORMANT until PG_* env vars are set + [warehouse] extra).

Phase 7. Implements the Connector interface via psycopg2. Read-only enforced by
sqlguard (connector layer) + the PreToolUse hook. Untested here because it needs a
live instance; a live `test_connection()` verifies it once creds exist.
"""
from __future__ import annotations

import os
import time
from typing import Any

from atlas.connectors.base import (
    ColumnSchema, ConnCheck, Connector, TableRef, TableSchema,
)
from atlas.lib.query_store import QueryStore


class PostgresConnector(Connector):
    dialect = "postgres"

    def __init__(self, name: str, raw: dict, store: QueryStore | None = None):
        super().__init__(name, store)
        self.raw = raw
        self.default_schema = raw.get("default_schema", "public")
        self.row_limit = raw.get("row_limit")
        self._conn = None

    def _connect(self):
        if self._conn is None:
            import psycopg2  # [warehouse] extra
            self._conn = psycopg2.connect(
                host=os.environ.get(self.raw.get("host_env", "")),
                port=os.environ.get(self.raw.get("port_env", "PG_PORT"), "5432"),
                user=os.environ.get(self.raw.get("user_env", "")),
                password=os.environ.get(self.raw.get("pass_env", "")),
                dbname=os.environ.get(self.raw.get("database_env", "")),
                connect_timeout=10,
            )
            self._conn.set_session(readonly=True, autocommit=True)  # belt & braces
        return self._conn

    def test_connection(self) -> ConnCheck:
        try:
            t0 = time.time()
            cur = self._connect().cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            # is the session actually read-only?
            cur.execute("SHOW default_transaction_read_only")
            ro = cur.fetchone()[0] == "on"
            return ConnCheck(True, f"{self.name} reachable", ro, (time.time() - t0) * 1000)
        except Exception as e:  # pragma: no cover
            return ConnCheck(False, str(e))

    def list_tables(self, schema: str | None = None) -> list[TableRef]:
        schema = schema or self.default_schema
        r = self.run(
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{schema}' ORDER BY table_name"
        )
        return [TableRef(name=row["table_name"], schema=schema) for row in r.rows]

    def get_schema(self, table: TableRef) -> TableSchema:
        r = self.run(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            f"WHERE table_schema = '{table.schema or self.default_schema}' "
            f"AND table_name = '{table.name}' ORDER BY ordinal_position"
        )
        cols = [ColumnSchema(row["column_name"], row["data_type"],
                             row["is_nullable"] == "YES") for row in r.rows]
        return TableSchema(table=table, columns=cols)

    def _execute(self, sql: str) -> tuple[list[dict[str, Any]], list[str], int | None]:
        cur = self._connect().cursor()
        cur.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        fetched = cur.fetchall()
        if self.row_limit and len(fetched) > self.row_limit:
            fetched = fetched[: self.row_limit]
        rows = [dict(zip(columns, r)) for r in fetched]
        return rows, columns, None  # postgres has no byte-scanned metric

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
