"""Semantic guardrails: a trust status for every column.

Downstream analysis agents read these to avoid unsafe fields and prefer the
repaired *_Clean columns. Statuses (spec 'Semantic Guardrails'):
  Trusted    — safe to use.
  Derived    — a repaired *_Clean column (preferred over its raw source).
  Deprecated — a raw column superseded by a *_Clean sibling (use the clean one).
  Unsafe     — a critical, unrepaired defect (e.g. an ambiguous column) — avoid.
  Blocked    — explicitly forbidden (e.g. flagged PII) — never select.
"""
from __future__ import annotations

from atlas.connectors.base import Connector, TableRef
from atlas.quality.detectors import detect_issues

TRUSTED, DERIVED, DEPRECATED, UNSAFE, BLOCKED = (
    "Trusted", "Derived", "Deprecated", "Unsafe", "Blocked")


def column_guardrails(con: Connector, table: TableRef,
                      blocked: set[str] | None = None) -> dict[str, str]:
    """Map each column to its trust status."""
    blocked = blocked or set()
    schema = con.get_schema(table)
    names = [c.name for c in schema.columns]
    nameset = set(names)
    status = {c: TRUSTED for c in names}

    for c in names:
        if c in blocked:
            status[c] = BLOCKED
        elif c.endswith("_Clean"):
            status[c] = DERIVED
        elif f"{c}_Clean" in nameset:
            status[c] = DEPRECATED

    # Unrepaired critical defect on a column that has no clean sibling -> Unsafe.
    for i in detect_issues(con, table):
        if (i.severity == "HIGH" and not i.structural and i.column
                and status.get(i.column) == TRUSTED and f"{i.column}_Clean" not in nameset):
            status[i.column] = UNSAFE
    return status


def safe_columns(con: Connector, table: TableRef) -> list[str]:
    """Columns an analyst may safely select (Trusted or Derived)."""
    g = column_guardrails(con, table)
    return [c for c, s in g.items() if s in (TRUSTED, DERIVED)]


def render_guardrails(con: Connector, table: TableRef) -> str:
    g = column_guardrails(con, table)
    order = {DERIVED: 0, TRUSTED: 1, DEPRECATED: 2, UNSAFE: 3, BLOCKED: 4}
    lines = [f"# Semantic guardrails — {table.qualified()}", "",
             "| column | status |", "|---|---|"]
    for c, s in sorted(g.items(), key=lambda kv: (order.get(kv[1], 9), kv[0])):
        lines.append(f"| {c} | {s} |")
    avoid = [c for c, s in g.items() if s in (UNSAFE, DEPRECATED, BLOCKED)]
    lines += ["", f"**Avoid downstream:** {avoid or 'none'} — prefer *_Clean fields."]
    return "\n".join(lines)
