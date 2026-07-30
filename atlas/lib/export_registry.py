"""Exporter registry — one output format per plugin.

`export_run()` used to be an if/elif ladder in which an unrecognised format string
produced *nothing* and reported success. That is the wrong failure mode for a system
whose first rule is that output must be trustworthy: asking for `"pbip"` and getting
a silent no-op is worse than an error.

Mirrors the `@register_copilot` / `@register` idioms the constitution names as the
extension mechanism: define an `Exporter`, decorate it, import it in the package
`__init__`. Nothing else changes.

`ExportContext` carries the run rather than a pile of positional arguments, because
different formats need different slices of it — comms needs the ledger and the deck
spec, the Power BI emitter needs the playbook result, the binding and a live
connector.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ExportContext", "Exporter", "UnknownExportFormat", "ExportUnavailable",
    "register_exporter", "get_exporter", "all_exporters", "EXPORTER_REGISTRY",
]


class UnknownExportFormat(Exception):
    """An export id nobody registered. Raised rather than silently skipped."""


class ExportUnavailable(Exception):
    """A registered exporter cannot run here (missing input, optional dep absent)."""


@dataclass
class ExportContext:
    run_id: str
    run_dir: Path
    state: object = None            # RunState
    ledger: object = None           # ProvenanceLedger
    spec: object = None             # DeckSpec
    playbook_id: str = ""
    result: object = None           # PlaybookResult
    binding: object = None          # ColumnBinding
    con: object = None              # Connector, when a live one is available
    options: dict = field(default_factory=dict)

    def write(self, rel: str, text: str) -> str:
        p = self.run_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return rel


class Exporter(ABC):
    id: str = ""
    description: str = ""
    # Named inputs that must be present on the context before `emit()` is called.
    requires: tuple[str, ...] = ()

    def available(self, ctx: ExportContext) -> tuple[bool, str]:
        missing = [r for r in self.requires if getattr(ctx, r, None) is None]
        if missing:
            return False, f"exporter '{self.id}' needs {missing} on the context"
        return True, ""

    @abstractmethod
    def emit(self, ctx: ExportContext) -> list[str]:
        """Write the format and return the relative artefact paths it produced."""


EXPORTER_REGISTRY: dict[str, Exporter] = {}


def register_exporter(cls):
    inst = cls()
    if not inst.id:
        raise ValueError(f"{cls.__name__} must define a non-empty id")
    if inst.id in EXPORTER_REGISTRY:
        raise ValueError(f"duplicate exporter id '{inst.id}'")
    EXPORTER_REGISTRY[inst.id] = inst
    return cls


def get_exporter(export_id: str) -> Exporter:
    exp = EXPORTER_REGISTRY.get(export_id)
    if exp is None:
        raise UnknownExportFormat(
            f"unknown export format '{export_id}'. Known: {sorted(EXPORTER_REGISTRY)}")
    return exp


def all_exporters() -> list[Exporter]:
    return [EXPORTER_REGISTRY[k] for k in sorted(EXPORTER_REGISTRY)]
