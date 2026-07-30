"""Binning a numeric column into buckets, and rendering those bins downstream.

`NTILE(k) OVER (ORDER BY col)` rather than `approx_quantile`: NTILE is exact and
deterministic, and each bucket's `min`/`max` fall out of the same query, so the cut
point Atlas reports is an *observed data value* rather than an estimated quantile.
`quantile_cont` would also be exact but returns interpolated edges that may not
exist in the data, which makes a reported threshold ("churn jumps at 16 days")
harder to defend.

The `edges_to_*` helpers exist so one set of cut points renders identically as a
label, a SQL CASE, and a DAX SWITCH. A bucket definition that drifts between the
analysis and the dashboard is the same class of bug as a metric definition that
drifts, so there is one source and three renderers.
"""
from __future__ import annotations

from atlas.lib.sqlident import quote_ident, quote_table
from atlas.lib.thresholds import Bucket

__all__ = [
    "ntile_sql", "value_group_sql", "buckets_from_rows", "should_group_by_value",
    "edges_to_labels", "edges_to_sql_case", "edges_to_dax_switch",
]


def should_group_by_value(distinct_count: int, k: int, *, row_count: int = 0,
                          min_bucket_n: int = 30, max_distinct: int = 60) -> bool:
    """Prefer grouping by raw value whenever each value has enough rows to stand alone.

    This is a precision decision, not a convenience one. A quantile bucket spanning
    several values *straddles* a cliff: on a 31-value column split into deciles, each
    bucket covers ~3 values, so a true cut at 16 gets reported as the bucket edge 15.
    Grouping by value reports the cut exactly, which matters because that number is
    what ends up in a bin label, a SQL CASE, and a dashboard.

    Two ways to qualify: fewer distinct values than buckets (quantiles would be
    meaningless), or few enough distinct values that every one clears `min_bucket_n`.
    """
    if distinct_count <= max(k, 2):
        return True
    if distinct_count <= max_distinct and row_count:
        return (row_count / distinct_count) >= min_bucket_n
    return False


def ntile_sql(table: str, col: str, target: str, k: int = 10, *,
              where: str = "") -> str:
    """Equal-count buckets with observed edges and the event rate per bucket."""
    t, c, y = quote_table(table), quote_ident(col), quote_ident(target)
    clause = f"{c} IS NOT NULL AND {y} IS NOT NULL"
    if where:
        clause += f" AND ({where})"
    return (
        f"WITH b AS (SELECT {c} AS v, CAST({y} AS DOUBLE) AS y, "
        f"NTILE({int(k)}) OVER (ORDER BY {c}) AS bucket FROM {t} WHERE {clause}) "
        f"SELECT bucket, count(*) AS n, min(v) AS lo, max(v) AS hi, "
        f"CAST(sum(y) AS BIGINT) AS x FROM b GROUP BY bucket ORDER BY bucket"
    )


def value_group_sql(table: str, col: str, target: str, *, where: str = "") -> str:
    """One bucket per distinct value — the low-cardinality path."""
    t, c, y = quote_table(table), quote_ident(col), quote_ident(target)
    clause = f"{c} IS NOT NULL AND {y} IS NOT NULL"
    if where:
        clause += f" AND ({where})"
    return (
        f"SELECT {c} AS lo, {c} AS hi, count(*) AS n, "
        f"CAST(sum(CAST({y} AS DOUBLE)) AS BIGINT) AS x "
        f"FROM {t} WHERE {clause} GROUP BY {c} ORDER BY {c}"
    )


def buckets_from_rows(rows: list[dict], *, lo_key: str = "lo", hi_key: str = "hi",
                      n_key: str = "n", x_key: str = "x",
                      index_key: str | None = "bucket") -> list[Bucket]:
    """Turn either bucket query's rows into `Bucket`s, ordered by value."""
    out: list[Bucket] = []
    ordered = sorted(rows, key=lambda r: float(r[lo_key]))
    for i, r in enumerate(ordered):
        idx = int(r[index_key]) if index_key and index_key in r else i + 1
        out.append(Bucket(index=idx, lo=float(r[lo_key]), hi=float(r[hi_key]),
                          n=int(r[n_key] or 0), x=int(r[x_key] or 0)))
    # Re-index densely so a caller never depends on NTILE's numbering surviving
    # a low-cardinality fallback.
    for i, b in enumerate(out):
        b.index = i + 1
    return out


def _fmt(v: float) -> str:
    """Render a cut point without a trailing `.0` when it is integral."""
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def edges_to_labels(edges: list[float]) -> list[str]:
    """Interior cut points -> human bin labels. [16, 21] -> 0-15 / 16-20 / 21+.

    Edges are treated as inclusive lower bounds of the bin above, matching
    `edges_to_sql_case` and `edges_to_dax_switch` exactly.
    """
    if not edges:
        return ["all"]
    e = sorted(float(x) for x in edges)
    labels = []
    integral = all(float(x).is_integer() for x in e)
    for i, cut in enumerate(e):
        if i == 0:
            upper = cut - 1 if integral else cut
            labels.append(f"<{_fmt(cut)}" if not integral else f"0-{_fmt(upper)}")
        else:
            prev = e[i - 1]
            upper = cut - 1 if integral else cut
            labels.append(f"{_fmt(prev)}-{_fmt(upper)}" if integral
                          else f"{_fmt(prev)}-{_fmt(cut)}")
    labels.append(f"{_fmt(e[-1])}+")
    return labels


def edges_to_sql_case(col: str, edges: list[float], labels: list[str]) -> str:
    c = quote_ident(col)
    if not edges:
        return f"'{labels[0]}'"
    parts = []
    e = sorted(float(x) for x in edges)
    for i, cut in enumerate(e):
        parts.append(f"WHEN {c} < {cut!r} THEN '{labels[i]}'")
    return "CASE " + " ".join(parts) + f" ELSE '{labels[-1]}' END"


def edges_to_dax_switch(col_ref: str, edges: list[float], labels: list[str]) -> str:
    """DAX `SWITCH(TRUE(), ...)` with the same boundaries as the SQL CASE.

    `col_ref` is a full DAX column reference, e.g. `Churn[Payment Delay]`.
    """
    if not edges:
        return f'"{labels[0]}"'
    e = sorted(float(x) for x in edges)
    lines = [f"    {col_ref} < {cut!r}, \"{labels[i]}\"" for i, cut in enumerate(e)]
    return "SWITCH(\n    TRUE(),\n" + ",\n".join(lines) + f",\n    \"{labels[-1]}\"\n)"
