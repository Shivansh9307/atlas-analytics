---
description: Register and test a data source (checks env-var creds, connection, read-only role).
argument-hint: <source-name-or-type>
---

Register and test the data source: **$ARGUMENTS**

1. Read `atlas/connectors/sources.yaml`. If the source is a dormant template,
   confirm which env vars it needs (by NAME) and check they are present in `.env`.
   Never print secret values.
2. Prefer an official **MCP server** where a mature one exists (Snowflake,
   Databricks, BigQuery toolbox); fall back to the documented Python driver
   (Postgres → psycopg2; local files → DuckDB). State which path is used and why.
3. Run the adapter's `test_connection()` via
   `uv run python -c "from atlas.connectors.registry import Registry; print(Registry().connector('$ARGUMENTS').test_connection())"`
   and report reachable? / read-only? / latency.
4. If creds are missing, list exactly what to add to `.env` (names only) and stop.
