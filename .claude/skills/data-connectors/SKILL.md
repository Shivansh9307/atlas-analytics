---
name: data-connectors
description: Connection registry, credential handling via env vars only, and connection tests for CSV/Excel/Postgres/Snowflake/BigQuery/Databricks/DuckDB. Use when registering, testing, or troubleshooting a data source.
---

# Data connectors

Uniform interface: `atlas/connectors/base.py::Connector`. Registry:
`atlas/connectors/registry.py` reads `atlas/connectors/sources.yaml`.

## Golden rules
- **Creds by env-var NAME only** in `sources.yaml`; real values live in gitignored
  `.env`. Never print secret values.
- **Read-only**: every read goes through `Connector.run()`, which asserts read-only
  (`atlas/lib/sqlguard.py`) and hashes+stores the result. Mutations are blocked at
  the connector AND the PreToolUse hook.
- **MCP-first**: prefer an official MCP server (Snowflake, Databricks, BigQuery
  toolbox) where one exists; else the documented Python driver (Postgres→psycopg2,
  files→DuckDB). Record which path a source uses in `sources.yaml` (`access:` key).

## Test a source
`uv run python .claude/skills/data-connectors/scripts/conn_test.py <source>`

## Adding a warehouse source
1. Uncomment its template in `sources.yaml`, set `*_env` keys to the env-var names.
2. Add those names to `.env` (values) and install the extra: `uv pip install -e ".[warehouse]"`.
3. `/connect <source>` to verify reachable / read-only / latency.

## Excel gotchas
`csv_duckdb.py` normalises Excel: multi-sheet (defaults to first, warns), merged/
unnamed headers (warns — grain may be ambiguous), phantom all-empty rows (dropped).
A warned workbook should be profiled before you trust its grain.
