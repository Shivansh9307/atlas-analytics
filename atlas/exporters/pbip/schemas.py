"""Verified PBIP / PBIR / TMDL constants — the single place format facts live.

Every URL and version here was checked against Microsoft documentation on
**2026-07-30** rather than recalled. They are versioned and they roll, so when a
Power BI Desktop release rejects a generated project, this file is the first place
to look and usually the only place to change.

Verification status, stated honestly:

| Constant | Source | Confidence |
|---|---|---|
| `PBIP_SCHEMA`, `PBISM_SCHEMA`, `PBIR_SCHEMA` | learn.microsoft.com projects-report + skills-for-fabric | verified, literal examples |
| `VERSION_SCHEMA`, `PAGES_SCHEMA`, `PAGE_SCHEMA` | fetched each schema document directly; required fields read off them | verified |
| `REPORT_SCHEMA` | learn.microsoft.com annotations example | verified |
| `VISUAL_SCHEMA` | published schema doc + a real emitted visual.json | verified |
| `PLATFORM_SCHEMA` | Git-integration system file; NOT verified against a live doc | **assumed** |
| `VISUAL_*` type ids | community examples, not an enumerated spec | **assumed** |

The assumed rows are the ones to check first on a load failure. `.platform` is Git
integration metadata and a project opens without it, so a wrong value there is
recoverable; a wrong `visualType` silently renders an empty visual, which is not.

Format status as of 2026-07: PBIR became the default report format in January 2026
(Power BI Desktop from the March 2026 release) and General Availability is planned
for Q3 2026 — so it is the current default but still formally in preview.
"""
from __future__ import annotations

_BASE = "https://developer.microsoft.com/json-schemas/fabric"

# --- project + item descriptors (verified) ---
PBIP_SCHEMA = f"{_BASE}/pbip/pbipProperties/1.0.0/schema.json"
PBISM_SCHEMA = f"{_BASE}/item/semanticModel/definitionProperties/1.0.0/schema.json"
PBIR_SCHEMA = f"{_BASE}/item/report/definitionProperties/2.0.0/schema.json"

# --- PBIR report definition (verified) ---
_RD = f"{_BASE}/item/report/definition"
VERSION_SCHEMA = f"{_RD}/versionMetadata/1.0.0/schema.json"
REPORT_SCHEMA = f"{_RD}/report/1.0.0/schema.json"
PAGES_SCHEMA = f"{_RD}/pagesMetadata/1.0.0/schema.json"
PAGE_SCHEMA = f"{_RD}/page/1.0.0/schema.json"
VISUAL_SCHEMA = f"{_RD}/visualContainer/2.4.0/schema.json"

# --- Git integration (assumed) ---
PLATFORM_SCHEMA = (f"{_BASE}/gitIntegration/platformProperties/2.0.0/schema.json")

# `version.json` must match ^[1-9][0-9]*\.(0|[1-9][0-9]*)\.0$ — read off the schema.
PBIR_VERSION = "1.0.0"
PBISM_VERSION = "4.2"
PBIR_DEFINITION_VERSION = "4.0"
PBIP_VERSION = "1.0"

# TMDL. Compatibility level 1567 is what current Power BI Desktop writes.
COMPATIBILITY_LEVEL = 1567
TMDL_INDENT = "\t"          # the docs are explicit: a single TAB, not spaces

# Canvas. 1280x720 is the Power BI default page size.
CANVAS_W = 1280
CANVAS_H = 720

# Visual type identifiers (assumed — see the table above).
VISUAL_CARD = "card"
VISUAL_COLUMN = "clusteredColumnChart"
VISUAL_BAR = "clusteredBarChart"
VISUAL_TABLE = "tableEx"
VISUAL_SLICER = "slicer"

# page.json displayOption enum.
DISPLAY_FIT_TO_PAGE = "FitToPage"
