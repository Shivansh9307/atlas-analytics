"""Output formats. Importing a module here registers its exporter.

Adding a format means adding a module and one import line — no core edit, matching
the repair-module and copilot plugin idioms.
"""
from __future__ import annotations

from atlas.lib.export_registry import (  # noqa: F401
    EXPORTER_REGISTRY, ExportContext, Exporter, ExportUnavailable,
    UnknownExportFormat, all_exporters, get_exporter, register_exporter,
)

from atlas.exporters import builtin        # noqa: F401,E402
from atlas.exporters import dax_measures   # noqa: F401,E402
from atlas.exporters import pbip           # noqa: F401,E402

__all__ = ["Exporter", "ExportContext", "UnknownExportFormat", "ExportUnavailable",
           "register_exporter", "get_exporter", "all_exporters", "EXPORTER_REGISTRY"]
