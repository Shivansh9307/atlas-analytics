---
name: data-repair
description: Detect data-quality issues, score quality across 10 dimensions, and apply safe, reversible repairs to a semantic clean layer (raw data untouched). Use when a source scores below Excellent, before trusting it for analysis, or when the user runs /clean.
---

# Data repair (Data Quality Copilot)

Implementation: `atlas/quality/`. Every probe runs through `Connector.run()`
(read-only, provenance-stamped). The clean layer is materialised via the
connector's `materialize_clean()` path — CREATE VIEW on the LOCAL DuckDB engine
only, never through `run()`, so the source guard stays intact and the source file
is only ever read. **Raw data is sacred: repairs only ADD `<col>_Clean` columns
(and optionally dedup rows); the original columns are never modified.**

## The 10-dimension quality score (`atlas/quality/score.py`)
Completeness · Consistency · Validity · Freshness · Uniqueness · Semantic Accuracy ·
Referential Integrity · Business Readiness · Type Safety · Documentation → weighted
0–100, banded Excellent (≥90) / Good (≥75) / Fair (≥60) / Poor.

## The 12 repair modules (`atlas/quality/modules/`, pluggable)
Date · Region (from Country) · Month · Quarter · Year · Duplicate · Country
Standardisation · Numeric Type · Boolean · Whitespace · Case · Null Classification.
Each detects issues and plans a reversible repair with confidence + business impact.
Config lives in `atlas/quality/rules/*.yaml` (never hardcoded).

## Workflow — `/clean <source> [flag]`
- **plan** (no flag) — detect + score + list proposed repairs.
- **--preview** — before→after score, rows affected, per-column samples, DDL.
- **--apply** — materialise `<table>_clean`; high-confidence repairs auto-apply,
  ambiguous ones (e.g. fiscal-vs-calendar `Quarter`) need `approve=True`. Writes the
  audit trail under `runs/<run_id>/repair/`.
- **--undo** — roll back the most recent repair (LIFO), re-materialise.
- **--history** — timestamp / repair / approval / rows affected / user.

## Readiness (the Data Readiness Gate)
A critical issue WITH an available repair is not a hard blocker — auto-apply the
confident ones, flag the rest as pending approval. Only report NOT READY when the
clean-layer score is below the floor or a critical issue has no repair path. Inside
`/analyze` this is the `quality` → `readiness_gate` stage; on a gate FAIL the run
BLOCKs and says exactly what to approve or fix.

## Supersession
On a clean layer, a raw column with a `<col>_Clean` sibling is superseded — detectors
and scoring skip it, so the score reflects the repaired state and downstream analysis
reads the clean fields.
