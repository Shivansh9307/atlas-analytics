"""Identifier quoting for generated SQL.

Real-world columns carry spaces, mixed case and reserved words — `Payment Delay`,
`Support Calls`, `Contract Length`. Playbooks build SQL by string composition, so
an unquoted identifier is not a style preference: it is a syntax error, or worse a
silent mis-parse (`SELECT Payment Delay` parses as `SELECT Payment AS Delay`).

Promoted out of `profiling.py`'s private `_q()` so there is exactly one quoting
rule in the codebase rather than one per module. Double-quoting with `"` -> `""`
escaping is the SQL standard and is correct for DuckDB, Postgres and Snowflake.

This is for identifiers only. Literal *values* must never be interpolated through
here — they belong in a parameterised query or a vetted literal builder.
"""
from __future__ import annotations

__all__ = ["quote_ident", "quote_table"]


def quote_ident(name: str) -> str:
    """Quote one identifier: `Payment Delay` -> `"Payment Delay"`."""
    if not isinstance(name, str) or not name:
        raise ValueError(f"identifier must be a non-empty string, got {name!r}")
    if "\x00" in name:
        raise ValueError(f"identifier contains a null byte: {name!r}")
    return '"' + name.replace('"', '""') + '"'


def quote_table(name: str) -> str:
    """Quote a possibly schema-qualified table: `main.my tbl` -> `"main"."my tbl"`.

    A dot is treated as a qualifier separator. An identifier that genuinely contains
    a dot must be passed already quoted (returned unchanged) — that case does not
    arise for any source Atlas registers today.
    """
    if not isinstance(name, str) or not name:
        raise ValueError(f"table name must be a non-empty string, got {name!r}")
    if name.startswith('"'):
        return name
    return ".".join(quote_ident(part) for part in name.split("."))
