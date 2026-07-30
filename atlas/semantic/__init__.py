"""Semantic layer: locked metric definitions resolved against metrics.yaml."""
from __future__ import annotations

import re
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


def known_metrics() -> list[str]:
    """Every locked metric key, for escalation messages that say what IS available."""
    return list(_load())


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


def metric_from_text(question: str) -> MetricDef | None:
    """Find the locked metric a free-text question refers to, by key or alias.

    Returns None when nothing matches, so the caller ESCALATES rather than falling
    back to a default. A silent default is how a churn question ends up answered
    with a gross-margin deck that passes every gate.

    Matching is word-boundary anchored (so 'cost' does not fire inside 'costume',
    and the two-letter 'gm' alias stays safe) and longest-alias-first, so
    'customer churn rate' wins over 'churn' and 'gross margin' over 'margin'.

    Known limitation: a question naming two metrics resolves to the longest
    matching alias rather than escalating on the ambiguity.
    """
    metrics = _load()
    # alias -> metric key. Built in metrics.yaml order so equal-length ties are
    # broken deterministically by declaration order (first wins).
    aliases: dict[str, str] = {}
    for mname, spec in metrics.items():
        for a in {mname.lower()} | {a.lower() for a in spec.get("aliases", [])}:
            aliases.setdefault(a, mname)

    q = question.lower()
    for alias in sorted(aliases, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", q):
            return resolve_metric(aliases[alias])
    return None
