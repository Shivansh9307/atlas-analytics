---
name: data-profiling
description: The standard data-quality profiling battery and how to read it into a GO/NO-GO verdict. Use before trusting any source for analysis.
---

# Data profiling

Implementation: `atlas/lib/profiling.py` (`profile_table`, `verdict_for`). Every
probe runs through `Connector.run()`, so profiling itself is provenance-stamped.

## The battery
- **row count** — is there data at all? (0 → NO-GO)
- **null rate per column** — >50% null on a key column is a red flag
- **distinct count + cardinality ratio** — spot constant columns and near-keys
- **grain / duplicate keys** — is the row set unique at the claimed grain? duplicate
  rows mean aggregates will double-count → confirm grain before summing
- **freshness** — max timestamp vs today, where a date column exists

## Reading the verdict
- `GO` — clean enough to answer.
- `GO-WITH-CAVEATS` — usable but declare the caveat (e.g. duplicates, high null) as
  an Assumption that flows to the deck appendix.
- `NO-GO` — cannot answer; report exactly what must change. Never push past a NO-GO
  with a confident deck (constitution rule 4).

Run: `/profile <source>` or call `profile_table` directly.
