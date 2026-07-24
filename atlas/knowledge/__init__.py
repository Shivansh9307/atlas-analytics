"""Business knowledge layer: glossary, organization facts, metric dictionary.

Complements the LOCKED metric formulas in atlas/semantic/metrics.yaml with the
plain-language context an analyst carries in their head — what a term means, whose
metric it is, what to watch for. `/business` and `/metrics` browse this; the context
loader injects a summary at session start.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from atlas.config import PATHS

KNOWLEDGE_DIR = PATHS.root / "atlas" / "knowledge"
GLOSSARY = KNOWLEDGE_DIR / "glossary.yaml"
BUSINESS = KNOWLEDGE_DIR / "business.yaml"


@dataclass
class Term:
    term: str
    definition: str
    aliases: list[str]
    category: str = ""
    metric: str | None = None


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) if path.exists() else {}


@lru_cache(maxsize=1)
def load_glossary() -> dict[str, Term]:
    data = _load_yaml(GLOSSARY)
    out: dict[str, Term] = {}
    for t in data.get("terms", []):
        out[t["term"].lower()] = Term(
            term=t["term"],
            definition=" ".join(str(t.get("definition", "")).split()),
            aliases=[a.lower() for a in t.get("aliases", [])],
            category=t.get("category", ""),
            metric=t.get("metric"),
        )
    return out


def resolve_term(text: str) -> Term | None:
    """Resolve a word/phrase to a glossary Term by name or alias."""
    key = text.strip().lower()
    glossary = load_glossary()
    if key in glossary:
        return glossary[key]
    for term in glossary.values():
        if key == term.term.lower() or key in term.aliases:
            return term
    return None


@lru_cache(maxsize=1)
def load_business() -> dict:
    return _load_yaml(BUSINESS)


def metric_owner(metric: str) -> str | None:
    notes = load_business().get("metric_notes", {})
    entry = notes.get(metric, {})
    return entry.get("owner_team")


def decision_owner_for(metric: str) -> str | None:
    """Which team's decision owner is accountable for this metric."""
    team = metric_owner(metric)
    if not team:
        return None
    for t in load_business().get("teams", []):
        if t.get("name") == team:
            return t.get("decision_owner")
    return None


def metric_dictionary() -> list[dict]:
    """Browsable metric entries: LOCKED formula + business context. Backs /metrics."""
    from atlas.semantic import _load as _load_metrics  # locked definitions

    glossary = load_glossary()
    notes = load_business().get("metric_notes", {})
    out = []
    for name, spec in _load_metrics().items():
        term = next((t for t in glossary.values() if t.metric == name), None)
        out.append({
            "metric": name,
            "expression": spec.get("expression"),
            "unit": spec.get("unit", "ratio"),
            "aliases": spec.get("aliases", []),
            "definition": term.definition if term else "",
            "owner_team": notes.get(name, {}).get("owner_team"),
            "decision_owner": decision_owner_for(name),
            "watch_for": notes.get(name, {}).get("watch_for", ""),
            "decomposition": spec.get("decomposition", "additive"),
        })
    return out


def clear_cache() -> None:
    load_glossary.cache_clear()
    load_business.cache_clear()
