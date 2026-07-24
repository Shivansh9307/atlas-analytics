---
description: Run data profiling only on a source and issue a GO / NO-GO verdict.
argument-hint: <source-name>
---

Profile the source **$ARGUMENTS** and issue a data-quality verdict.

Delegate to the `source-profiler` agent, or run directly:
`uv run python -c "from atlas.connectors.registry import Registry; from atlas.lib.profiling import profile_table, verdict_for; from atlas.connectors.base import TableRef; c=Registry().connector('$ARGUMENTS'); r=profile_table(c, TableRef(c.table_name)); print(verdict_for(r).line())"`

Report row count, null rates, cardinality, grain/duplicate findings, freshness,
and the final `GO` / `GO-WITH-CAVEATS` / `NO-GO` line with its reason.
