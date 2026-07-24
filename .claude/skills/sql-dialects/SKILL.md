---
name: sql-dialects
description: Syntax and cost differences across Snowflake / Postgres / Databricks / BigQuery / DuckDB, plus window-function gotchas. Use when authoring queries for a specific warehouse.
---

# SQL dialects

Author read-only, cost-aware SQL. Per-dialect detail in `reference/`.

## Cost patterns (the money slide)
- **BigQuery**: billed by bytes scanned. SELECT only needed columns; filter on the
  partition column; use `--dry_run` / `estimate_bytes()` before running wide scans.
- **Snowflake**: prune with clustering keys; avoid `SELECT *`; watch warehouse size.
- **Databricks**: filter partition columns; Z-ORDER awareness; avoid cross-joins.
- **Postgres**: use indexes; `EXPLAIN` before heavy joins; `LIMIT` on exploration.
- **DuckDB** (local files): cheap; still `LIMIT` exploration for speed.

## Portability gotchas
- date truncation: `DATE_TRUNC` (PG/Snowflake/DuckDB) vs `TIMESTAMP_TRUNC` (BQ).
- quarter: `EXTRACT(QUARTER FROM d)` widely; verify BQ.
- window frames: default frame differs; always state `ROWS BETWEEN …` for running sums.
- NULL ordering: `NULLS LAST` explicit — engines differ on default.
- string quoting: single quotes for literals; identifiers double-quoted (PG/DuckDB)
  vs backticks (BQ/Databricks).

## Always
- Never `SELECT *` on a warehouse table.
- Exploration: `LIMIT` and/or sample. Final headline: full scan, exact.
- Route through `Connector.run()` so it is hashed, stored, and read-only-checked.
