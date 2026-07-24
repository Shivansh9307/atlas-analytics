"""Session context loader.

Bundles everything the analyst team should know before touching a source: the active
schema, source quirks, the business glossary, the metric dictionary, recent lessons,
and how many proven queries exist to reuse. Rendered to markdown for injection at
session start (the knowledge-bootstrap idea) or into an agent's prompt.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from atlas.config import PATHS
from atlas.connectors.base import TableRef
from atlas.knowledge import load_business, load_glossary, metric_dictionary
from atlas.lib import query_archive


@dataclass
class Context:
    source: str
    schema: list[dict] = field(default_factory=list)
    quirks: str = ""
    glossary: list[dict] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)
    lessons: list[dict] = field(default_factory=list)
    archive_available: int = 0
    org: str = ""

    def render(self) -> str:
        lines = [f"# Active context — {self.source}", ""]
        if self.org:
            lines += [f"**Organization:** {self.org}", ""]
        if self.schema:
            lines += ["## Schema"]
            lines += [f"- `{c['name']}` ({c['dtype']})" for c in self.schema]
            lines.append("")
        if self.quirks.strip():
            lines += ["## Source quirks", self.quirks.strip(), ""]
        if self.metrics:
            lines += ["## Metric dictionary"]
            for m in self.metrics:
                owner = f" — owner: {m['owner_team']}" if m.get("owner_team") else ""
                lines.append(f"- **{m['metric']}** = `{m['expression']}`{owner}")
                if m.get("watch_for"):
                    lines.append(f"  - watch: {m['watch_for']}")
            lines.append("")
        if self.glossary:
            lines += ["## Glossary"]
            lines += [f"- **{t['term']}**: {t['definition']}" for t in self.glossary]
            lines.append("")
        if self.lessons:
            lines += ["## Recent lessons"]
            lines += [f"- {l.get('rule', '')}" for l in self.lessons[:8]]
            lines.append("")
        lines += [f"_Proven queries available to reuse: {self.archive_available}_"]
        return "\n".join(lines)


def _quirks_for(source: str) -> str:
    p = PATHS.quirks / f"{source}.md"
    return p.read_text() if p.exists() else ""


def _recent_lessons(limit: int = 8) -> list[dict]:
    p = PATHS.lessons_jsonl
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    return rows[-limit:]


def load_context(source: str, connector=None) -> Context:
    """Assemble the context bundle for `source`. Pass a connector to include schema."""
    schema: list[dict] = []
    if connector is not None:
        try:
            table = getattr(connector, "table_name", None) or source
            ts = connector.get_schema(TableRef(table))
            schema = [{"name": c.name, "dtype": c.dtype} for c in ts.columns]
        except Exception:
            schema = []

    glossary = [
        {"term": t.term, "definition": t.definition}
        for t in load_glossary().values()
    ]
    biz = load_business()
    return Context(
        source=source,
        schema=schema,
        quirks=_quirks_for(source),
        glossary=glossary,
        metrics=metric_dictionary(),
        lessons=_recent_lessons(),
        archive_available=query_archive.stats().get("total", 0),
        org=(biz.get("organization", {}) or {}).get("name", ""),
    )
