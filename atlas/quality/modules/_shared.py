"""Shared detection helpers for repair modules (all reads via guarded run())."""
from __future__ import annotations

from atlas.connectors.base import Connector, TableSchema
from atlas.quality.modules.base import is_text, q


def date_parse_rate(con: Connector, tname: str, column: str) -> float:
    """Fraction of non-null values in `column` that TRY_CAST to DATE cleanly."""
    r = con.run(
        f"SELECT count({q(column)}) AS nn, count(TRY_CAST({q(column)} AS DATE)) AS ok "
        f"FROM {tname}"
    ).rows[0]
    nn = r["nn"] or 0
    return (r["ok"] or 0) / nn if nn else 0.0


def find_date_column(con: Connector, tname: str, schema: TableSchema,
                     min_parse_rate: float = 0.99) -> tuple[str, bool] | None:
    """Best date column as (name, needs_cast).

    Prefers a real DATE/TIMESTAMP column; else a text column that parses as DATE
    at >= min_parse_rate. Name containing 'date' breaks ties (stable, determinstic).
    """
    real: list[str] = []
    text_candidates: list[tuple[str, float]] = []
    for c in schema.columns:
        u = c.dtype.upper()
        if u.startswith(("DATE", "TIMESTAMP")):
            real.append(c.name)
        elif is_text(c.dtype):
            pr = date_parse_rate(con, tname, c.name)
            if pr >= min_parse_rate:
                text_candidates.append((c.name, pr))

    def _rank(name: str) -> tuple[int, str]:
        return (0 if "date" in name.lower() else 1, name)

    if real:
        return (sorted(real, key=_rank)[0], False)
    if text_candidates:
        name = sorted((n for n, _ in text_candidates), key=_rank)[0]
        return (name, True)
    return None


def date_expr(column: str, needs_cast: bool) -> str:
    """A DuckDB expression yielding a DATE from `column`."""
    return f"TRY_CAST({q(column)} AS DATE)" if needs_cast else q(column)


def mismatch_count(con: Connector, tname: str, derived_expr: str, stored_col: str) -> tuple[int, int]:
    """(#rows where derived != stored, #rows where both present)."""
    r = con.run(
        f"SELECT "
        f"  sum(CASE WHEN {derived_expr} IS NOT NULL AND {q(stored_col)} IS NOT NULL "
        f"           AND CAST({derived_expr} AS VARCHAR) <> CAST({q(stored_col)} AS VARCHAR) "
        f"      THEN 1 ELSE 0 END) AS mism, "
        f"  sum(CASE WHEN {derived_expr} IS NOT NULL AND {q(stored_col)} IS NOT NULL "
        f"      THEN 1 ELSE 0 END) AS both "
        f"FROM {tname}"
    ).rows[0]
    return int(r["mism"] or 0), int(r["both"] or 0)


def find_column(schema: TableSchema, *names: str) -> str | None:
    """First column whose name case-insensitively equals one of `names`."""
    want = {n.lower() for n in names}
    for c in schema.columns:
        if c.name.lower() in want:
            return c.name
    return None
