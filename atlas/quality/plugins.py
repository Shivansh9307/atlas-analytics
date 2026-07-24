"""Copilot plugin framework.

The Data Quality Copilot is the first of many specialist copilots. Any future
copilot (Governance, GDPR, PII, Forecast, Dashboard, ML, Data Steward, Metadata,
Schema Drift — spec 'Plugin Framework') registers here via @register_copilot and
becomes discoverable/runnable WITHOUT editing core code. This mirrors the repair-
module registry (atlas/quality/modules/base.py) one level up.

Contract: a Copilot exposes `id`, `description`, and `run(con, table, source,
run_dir) -> dict` (a JSON-serialisable summary). It must be read-only to sources
and route every probe through `Connector.run()`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from atlas.connectors.base import Connector, TableRef


class Copilot(ABC):
    id: str = "base"
    description: str = ""

    @abstractmethod
    def run(self, con: Connector, table: TableRef, source: str,
            run_dir: Path | None = None) -> dict:
        ...


COPILOT_REGISTRY: dict[str, Copilot] = {}


def register_copilot(cls):
    inst = cls()
    COPILOT_REGISTRY[inst.id] = inst
    return cls


def get_copilot(copilot_id: str) -> Copilot | None:
    return COPILOT_REGISTRY.get(copilot_id)


def all_copilots() -> list[Copilot]:
    return [COPILOT_REGISTRY[k] for k in sorted(COPILOT_REGISTRY)]


@register_copilot
class DataQualityCopilot(Copilot):
    id = "data-quality"
    description = ("Profiles, scores 10 quality dimensions, detects issues, and "
                  "applies safe reversible repairs to a semantic clean layer.")

    def run(self, con, table, source, run_dir=None) -> dict:
        from atlas.quality.pipeline import run_copilot
        return run_copilot(con, table, source=source, run_dir=run_dir).as_dict()
