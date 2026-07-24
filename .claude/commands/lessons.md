---
description: Search the lesson store, optionally by tag.
argument-hint: "[tag]"
---

Search Atlas lessons for: **$ARGUMENTS** (empty = list all).

Read `memory/lessons.jsonl`. Filter by tag if one is given (tags look like
`source:snowflake`, `metric:gross_margin`, `agent:sql-engineer`, `class:filter-leakage`).
For each match show: `id`, trigger, rule, `times_prevented`, and whether it has
been **promoted** to a hard artefact (locked metric / quirk / hook rule / query
assertion) or is still a best-effort prompt injection.
