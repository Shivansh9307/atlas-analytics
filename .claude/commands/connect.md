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
5. For a resilient connect that survives a warehouse outage, use the fallback chain —
   it tries the primary adapter, then a declared local DuckDB/CSV, and **reports the
   active source** so the user always knows which data answered:
   `uv run python -c "from atlas.connectors.registry import Registry; r=Registry().resolve('$ARGUMENTS'); print('active:', r.active, '| chain:', r.chain)"`
   Declare a fallback in `sources.yaml` with `fallback: {csv_path|duckdb_path, table_name}`.

**Wizard mode** (no argument / new source): walk the user through picking a type
(CSV/DuckDB/Postgres/Snowflake/BigQuery/Databricks), collect the env-var NAMES to set,
add the source to `sources.yaml`, `/profile` it, and record quirks. Then confirm it
with the `resolve()` call above.
