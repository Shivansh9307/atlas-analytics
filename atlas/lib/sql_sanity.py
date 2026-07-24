"""SQL result sanity checks — correctness guards that complement provenance.

Provenance proves a number came from a query; these prove the query didn't quietly
do something wrong (fan-out joins, parts that don't sum, out-of-range dates, dup
keys, missing periods). Pure functions over result rows (list[dict]).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def check_percentages_sum(rows: list[dict], pct_key: str, *,
                          expected: float = 100.0, tol: float = 0.5) -> Check:
    total = sum(float(r[pct_key]) for r in rows)
    ok = abs(total - expected) <= tol
    return Check("percentages_sum", ok,
                 f"sum({pct_key})={total:.4f}, expected {expected}±{tol}")


def check_no_duplicate_keys(rows: list[dict], keys: list[str]) -> Check:
    seen: set[tuple] = set()
    dups = 0
    for r in rows:
        k = tuple(r[c] for c in keys)
        if k in seen:
            dups += 1
        seen.add(k)
    return Check("no_duplicate_keys", dups == 0,
                 f"{dups} duplicate row(s) on key {keys}")


def check_date_bounds(rows: list[dict], date_key: str, lo, hi) -> Check:
    out = [r[date_key] for r in rows if not (lo <= r[date_key] <= hi)]
    return Check("date_bounds", not out,
                 f"{len(out)} row(s) outside [{lo}, {hi}]")


def check_join_cardinality(left: list[dict], joined: list[dict], key: str,
                           *, max_fanout: float = 1.0) -> Check:
    """Detect an unexpected fan-out: joined rows per distinct left key.

    max_fanout=1.0 asserts a one-to-one/one-to-none join. A ratio above it means the
    join multiplied rows (a classic silent double-count).
    """
    left_keys = {r[key] for r in left}
    if not left_keys:
        return Check("join_cardinality", True, "no left rows")
    ratio = len(joined) / len(left_keys)
    return Check("join_cardinality", ratio <= max_fanout + 1e-9,
                 f"{ratio:.3f} joined rows per left key (max {max_fanout})")


def check_temporal_coverage(rows: list[dict], period_key: str,
                            expected_periods: list) -> Check:
    present = {r[period_key] for r in rows}
    missing = [p for p in expected_periods if p not in present]
    return Check("temporal_coverage", not missing,
                 f"missing periods: {missing}" if missing else "all periods present")


def run_all(checks: list[Check]) -> dict:
    failed = [c.name for c in checks if not c.ok]
    return {"passed": not failed, "failed": failed,
            "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks]}
