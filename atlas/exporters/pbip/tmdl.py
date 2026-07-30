"""TMDL semantic-model emission.

TMDL uses **tab** indentation with exactly three meaningful levels — object
declaration, object properties, multi-line expressions — and the docs are explicit
that not following the indentation rules is a parse error, not a formatting nit. So
indentation here is generated, never hand-typed into a string literal.

Names containing whitespace, dots, colons, equals or single quotes must be wrapped in
single quotes; `quote_name()` is the one place that rule lives. Column names in this
project routinely contain spaces (`Payment Delay`), so it fires constantly.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from atlas.exporters.pbip.schemas import COMPATIBILITY_LEVEL, TMDL_INDENT as T

__all__ = ["TmdlColumn", "TmdlTable", "quote_name", "render_table", "render_model",
           "render_database", "render_relationships", "dtype_to_tmdl", "m_csv_partition"]

_NEEDS_QUOTES = set(" .:='\t")


def quote_name(name: str) -> str:
    """Single-quote a TMDL object name when the grammar requires it."""
    s = str(name)
    if any(ch in _NEEDS_QUOTES for ch in s) or not s:
        return "'" + s.replace("'", "''") + "'"
    return s


def dtype_to_tmdl(dtype: str) -> str:
    """Map a DuckDB/warehouse dtype onto a TMDL dataType."""
    d = (dtype or "").upper()
    if d.startswith(("TINYINT", "SMALLINT", "INTEGER", "INT", "BIGINT", "HUGEINT")):
        return "int64"
    if d.startswith(("DECIMAL", "NUMERIC")):
        return "decimal"
    if d.startswith(("FLOAT", "DOUBLE", "REAL")):
        return "double"
    if d.startswith("BOOL"):
        return "boolean"
    if d.startswith(("TIMESTAMP", "DATETIME")):
        return "dateTime"
    if d.startswith("DATE"):
        return "dateTime"
    return "string"


@dataclass
class TmdlColumn:
    name: str
    dtype: str = "string"
    summarize_by: str = "none"
    description: str = ""
    is_hidden: bool = False
    format_string: str = ""

    def render(self) -> str:
        lines = []
        for d in self.description.splitlines():
            lines.append(f"{T}/// {d}")
        lines.append(f"{T}column {quote_name(self.name)}")
        lines.append(f"{T}{T}dataType: {dtype_to_tmdl(self.dtype)}")
        if self.is_hidden:
            lines.append(f"{T}{T}isHidden")
        lines.append(f"{T}{T}summarizeBy: {self.summarize_by}")
        lines.append(f"{T}{T}sourceColumn: {self.name}")
        if self.format_string:
            lines.append(f"{T}{T}formatString: {self.format_string}")
        lines.append(f"{T}{T}lineageTag: {uuid.uuid5(uuid.NAMESPACE_OID, self.name)}")
        return "\n".join(lines)


@dataclass
class TmdlTable:
    name: str
    columns: list[TmdlColumn] = field(default_factory=list)
    measures: list = field(default_factory=list)     # DaxMeasure
    partition_m: str = ""
    description: str = ""
    calculated_columns: list[tuple[str, str, str]] = field(default_factory=list)
    # (name, DAX expression, description)


def m_csv_partition(csv_path: str, *, columns: list[TmdlColumn]) -> str:
    """Power Query M that loads a CSV and types its columns.

    A relative path is used so the project stays portable; Power BI resolves it
    against the .pbip location. `Encoding=65001` is UTF-8.
    """
    types = ", ".join(
        f'{{"{c.name}", {_m_type(dtype_to_tmdl(c.dtype))}}}' for c in columns)
    escaped = str(csv_path).replace('"', '""')
    return (
        "let\n"
        f'    Source = Csv.Document(File.Contents("{escaped}"),'
        '[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n'
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),\n"
        f"    Typed = Table.TransformColumnTypes(Promoted, {{{types}}})\n"
        "in\n"
        "    Typed"
    )


def _m_type(tmdl_type: str) -> str:
    return {"int64": "Int64.Type", "double": "type number", "decimal": "type number",
            "boolean": "type logical", "dateTime": "type datetime"}.get(
                tmdl_type, "type text")


def render_table(t: TmdlTable) -> str:
    """One .tmdl file for a table: columns, calculated columns, measures, partition."""
    out = []
    for d in t.description.splitlines():
        out.append(f"/// {d}")
    out.append(f"table {quote_name(t.name)}")
    out.append(f"{T}lineageTag: {uuid.uuid5(uuid.NAMESPACE_OID, t.name)}")
    out.append("")

    for c in t.columns:
        out.append(c.render())
        out.append("")

    for name, dax, desc in t.calculated_columns:
        for d in (desc or "").splitlines():
            out.append(f"{T}/// {d}")
        # A calculated column's default property is its DAX expression.
        out.append(f"{T}column {quote_name(name)} = {_inline(dax)}")
        out.append(f"{T}{T}summarizeBy: none")
        out.append(f"{T}{T}lineageTag: {uuid.uuid5(uuid.NAMESPACE_OID, name)}")
        out.append("")

    for m in t.measures:
        for d in (m.description or "").splitlines():
            out.append(f"{T}/// {d}")
        expr = m.expression.strip()
        if "\n" in expr:
            # Multi-line expressions must sit one level deeper than the properties.
            out.append(f"{T}measure {quote_name(m.name)} =")
            for line in expr.splitlines():
                out.append(f"{T}{T}{T}{line}")
        else:
            out.append(f"{T}measure {quote_name(m.name)} = {expr}")
        if m.format_string:
            out.append(f"{T}{T}formatString: {m.format_string}")
        out.append(f"{T}{T}lineageTag: {uuid.uuid5(uuid.NAMESPACE_OID, m.name)}")
        out.append("")

    if t.partition_m:
        out.append(f"{T}partition {quote_name(t.name + '-partition')} = m")
        out.append(f"{T}{T}mode: import")
        out.append(f"{T}{T}source =")
        for line in t.partition_m.splitlines():
            out.append(f"{T}{T}{T}{line}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def _inline(dax: str) -> str:
    return " ".join(str(dax).split())


def render_database(name: str) -> str:
    return (f"database {quote_name(name)}\n"
            f"{T}compatibilityLevel: {COMPATIBILITY_LEVEL}\n")


def render_model(table_names: list[str], *, culture: str = "en-US",
                 annotations: dict[str, str] | None = None) -> str:
    """model.tmdl. `ref table` preserves collection ordering across a round-trip."""
    out = ["model Model", f"{T}culture: {culture}",
           f"{T}defaultPowerBIDataSourceVersion: powerBI_V3",
           f"{T}discourageImplicitMeasures", ""]
    for k, v in (annotations or {}).items():
        out.append(f"annotation {k} = {v}")
    if annotations:
        out.append("")
    for n in table_names:
        out.append(f"ref table {quote_name(n)}")
    return "\n".join(out) + "\n"


def render_relationships(rels: list[tuple[str, str, str, str]]) -> str:
    """relationships.tmdl from (from_table, from_col, to_table, to_col) tuples."""
    out = []
    for ft, fc, tt, tc in rels:
        rid = uuid.uuid5(uuid.NAMESPACE_OID, f"{ft}.{fc}->{tt}.{tc}")
        out.append(f"relationship {rid}")
        out.append(f"{T}fromColumn: {quote_name(ft)}.{quote_name(fc)}")
        out.append(f"{T}toColumn: {quote_name(tt)}.{quote_name(tc)}")
        out.append("")
    return "\n".join(out)
