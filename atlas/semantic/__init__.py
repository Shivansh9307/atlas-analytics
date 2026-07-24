"""Semantic layer: locked metric definitions resolved against metrics.yaml."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from atlas.config import PATHS


class MetricAmbiguity(Exception):
    """Raised when a requested metric cannot be resolved to a locked definition."""


@dataclass
class MetricDef:
    name: str
    expression: str
    unit: str
    grain: list[str]
    decomposition: str
    decomposable_by: list[str]
    raw: dict


def _load() -> dict:
    data = yaml.safe_load(Path(PATHS.metrics_yaml).read_text()) or {}
    return data.get("metrics", {})


def resolve_metric(name: str) -> MetricDef:
    """Resolve a possibly-fuzzy metric name to its LOCKED definition.

    Never invents a formula. If the name matches nothing (by key or alias),
    raises MetricAmbiguity so the pipeline escalates rather than guessing.
    """
    metrics = _load()
    key = name.strip().lower()
    for mname, spec in metrics.items():
        aliases = {mname.lower()} | {a.lower() for a in spec.get("aliases", [])}
        if key in aliases:
            return MetricDef(
                name=mname,
                expression=spec["expression"],
                unit=spec.get("unit", "ratio"),
                grain=spec.get("grain", []),
                decomposition=spec.get("decomposition", "additive"),
                decomposable_by=spec.get("decomposable_by", []),
                raw=spec,
            )
    raise MetricAmbiguity(
        f"metric '{name}' not found in metrics.yaml. Known: {list(metrics)}. "
        "Escalate for a locked definition rather than guessing."
    )
