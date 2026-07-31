#!/usr/bin/env python3
"""Pre-model redundancy check: the assertion that L-0004/L-0005/L-0006/L-0007 promote to.

Why this exists: on 2026-07-31 a LogisticPlaybook fit against a 36-column joined
star-schema view failed FIVE times in a row, each time for a different instance of
the same family of mistakes — a coarse dimension attribute kept alongside the fine
one it is an exact function of, an accidental duplicate numeric, a partially-nested
categorical, and finally a status column that made the target quasi-separable. Each
failure cost a full run because the offending column was found by guessing after the
fit blew up. Every one of them is decidable *before* the first fit, from the data.

Four checks, cheapest first:

  1. FUNCTIONAL DETERMINISM  — A determines B (each value of A maps to exactly one
     value of B). B's one-hot dummies are then exact linear combinations of A's.
  2. EXACT DUPLICATE         — A determines B *and* B determines A (a relabelling,
     e.g. store_id/store_name, or a coincidence in this extract like
     num_distinct_products == num_line_items).
  3. DESIGN-MATRIX RANK      — encode exactly the way the engine does
     (atlas.lib.logit.build_design, drop_first=True) and require full column rank.
     Checks 1-2 are necessary but NOT sufficient: a brand that sits inside exactly
     one subcategory is collinear even though brand does not determine subcategory.
  4. QUASI-SEPARATION SCREEN — a categorical level (or its complement) on which the
     target is constant lets the MLE diverge: "logistic fit did not converge", a
     different symptom of the same "column too entangled with the outcome" mistake.

Read-only throughout: every query goes through Connector.run().

Usage:
  redundancy_check.py --source <source_id> [--table <table>] --target <col>
                      [--entity <col>] [--exclude a,b,c] [--max-rows N] [--quiet]
  redundancy_check.py --source <source_id> --plan runs/<run_id>/feature_plan.json

Exit codes: 0 = clean, 1 = redundancy found (do not fit yet), 2 = usage/other error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from atlas.connectors.base import TableRef  # noqa: E402
from atlas.connectors.registry import Registry  # noqa: E402
from atlas.lib.logit import build_design  # noqa: E402
from atlas.playbooks.base import FeaturePlan  # noqa: E402
from atlas.playbooks.binding import probe_columns, split_features  # noqa: E402


def _codes(values: list) -> np.ndarray:
    """Integer-code a column (None is its own level) for fast pair arithmetic."""
    lookup: dict = {}
    out = np.empty(len(values), dtype=np.int64)
    for i, v in enumerate(values):
        key = "\0NULL" if v is None else str(v)
        out[i] = lookup.setdefault(key, len(lookup))
    return out


def _determines(a: np.ndarray, b: np.ndarray) -> bool:
    """True if each value of `a` maps to exactly one value of `b`."""
    na = int(a.max()) + 1
    nb = int(b.max()) + 1
    pairs = a.astype(np.int64) * nb + b.astype(np.int64)
    return np.unique(pairs).size == na


def check_pairs(rows: list[dict], categorical: list[str],
                numeric: list[str]) -> tuple[list, list]:
    """Checks 1 and 2. Returns (determinism findings, duplicate findings).

    Determinism is only tested between columns that get ONE-HOT ENCODED, because that
    is when "A determines B" implies B's dummies are a linear combination of A's. A
    continuous numeric with near-unique values trivially "determines" every other
    column and means nothing here — its collinearity, if any, is the rank check's job.
    Continuous numerics are instead compared for exact equality (the accidental
    duplicate that only exists in this extract).
    """
    # A numeric with few distinct values is, for collinearity purposes, a categorical:
    # it is an exact linear function of that column's dummies (store_id over
    # store_name is the canonical case), so include it in the determinism sweep.
    lowcard = [c for c in numeric
               if len({r.get(c) for r in rows}) <= min(50, max(2, len(rows) // 10))]
    encoded = sorted(set(categorical) | set(lowcard))
    coded = {c: _codes([r.get(c) for r in rows]) for c in encoded}
    ndv = {c: int(coded[c].max()) + 1 for c in encoded}
    determ, dupes = [], []
    for i, a in enumerate(encoded):
        for b in encoded[i + 1:]:
            ab = _determines(coded[a], coded[b])
            ba = _determines(coded[b], coded[a])
            if ab and ba:
                dupes.append((a, b, ndv[a]))
            elif ab:
                determ.append((a, b, ndv[a], ndv[b]))
            elif ba:
                determ.append((b, a, ndv[b], ndv[a]))

    vals = {c: np.array([float(r[c]) if r.get(c) is not None else np.nan for r in rows])
            for c in numeric}
    for i, a in enumerate(numeric):
        for b in numeric[i + 1:]:
            if np.array_equal(vals[a], vals[b], equal_nan=True):
                dupes.append((a, b, len(np.unique(vals[a]))))
    return determ, dupes


def check_rank(rows: list[dict], plan: FeaturePlan
               ) -> tuple[int, int, list[tuple]]:
    """Check 3. Returns (rank, n_columns, [(source column, n dependent dummies, n dummies
    in its block, example dependent dummy names, the columns it is entangled with)]).

    Uses an unpivoted QR on the column-normalised design: Householder QR puts a ~0 on
    R's diagonal exactly where a column is a linear combination of the columns BEFORE
    it, which names the offending dummies instead of only the offending block. That
    matters for a partially-nested categorical (a brand confined to one subcategory):
    only a few of its dummies are dependent, so block-wise removal never finds it.
    """
    dm = build_design(rows, plan, standardize=True, drop_first=True)
    if not dm.X:
        raise ValueError(
            f"no rows have a non-null '{plan.target}' — is that really the target "
            f"column of {plan.table}?")
    X = np.asarray(dm.X, dtype=float)
    X = np.hstack([np.ones((X.shape[0], 1)), X])          # intercept, as fit_logit does
    names = ["__intercept__"] + list(dm.feature_names)
    src = {n: dm.source_of.get(n, n) for n in dm.feature_names}
    src["__intercept__"] = "(intercept)"
    rank, ncol = int(np.linalg.matrix_rank(X)), X.shape[1]
    if rank == ncol:
        return rank, ncol, []

    norms = np.linalg.norm(X, axis=0)
    norms[norms == 0] = 1.0
    diag = np.abs(np.diag(np.linalg.qr(X / norms, mode="r")))
    tol = 1e-9 * max(1.0, float(diag.max()))
    dependent = [names[j] for j in range(ncol) if diag[j] < tol]

    per_block: dict[str, list[str]] = {}
    partners: dict[str, set[str]] = {}
    for n in dependent:
        per_block.setdefault(src[n], []).append(n)
        # Which earlier columns actually form the combination? Naming the partner is
        # what tells the analyst WHICH side of the pair to drop.
        j = names.index(n)
        coef, *_ = np.linalg.lstsq(X[:, :j], X[:, j], rcond=None)
        for k, c in enumerate(coef):
            if abs(c) > 1e-8 and src[names[k]] not in (src[n], "(intercept)"):
                partners.setdefault(src[n], set()).add(src[names[k]])
    sizes: dict[str, int] = {}
    for n in names:
        sizes[src[n]] = sizes.get(src[n], 0) + 1
    return rank, ncol, [(c, len(v), sizes[c], v[:4], sorted(partners.get(c, set())))
                        for c, v in sorted(per_block.items(), key=lambda kv: -len(kv[1]))]


def check_separation(rows: list[dict], plan: FeaturePlan) -> list[tuple[str, str, int]]:
    """Check 4: categorical levels on which the target never varies."""
    tgt = plan.target
    flags = []
    for c in plan.categorical:
        by: dict[str, set] = {}
        for r in rows:
            if r.get(tgt) is None:
                continue
            by.setdefault(str(r.get(c)), set()).add(int(float(r[tgt])))
        if len(by) < 2:
            continue
        constant = [lv for lv, vals in by.items() if len(vals) == 1]
        # Only interesting when the target is constant over levels covering most rows:
        # a single tiny level is a small-sample artefact, not separation.
        if constant and len(constant) >= len(by) - 1:
            n = sum(1 for r in rows if str(r.get(c)) in constant)
            flags.append((c, ",".join(sorted(constant)[:4]), n))
    return flags


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True)
    ap.add_argument("--table")
    ap.add_argument("--target")
    ap.add_argument("--entity", default="")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--plan", help="a runs/<id>/feature_plan.json to re-check")
    ap.add_argument("--max-rows", type=int, default=0)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    con = Registry().connector(a.source)
    if a.plan:
        raw = json.loads(Path(a.plan).read_text())
        table, target = raw["table"], raw["target"]
        entity = raw.get("entity", "")
        numeric, categorical = list(raw["numeric"]), list(raw["categorical"])
    else:
        if not a.target:
            ap.error("--target is required unless --plan is given")
        table = a.table or getattr(con, "table_name", a.source)
        target, entity = a.target, a.entity
        schema = con.get_schema(TableRef(table))
        probes = probe_columns(con, table, schema)
        drop = {target, entity} | {c for c in a.exclude.split(",") if c}
        numeric, categorical, _ = split_features(probes, exclude=drop)

    cols = {c.name for c in con.get_schema(TableRef(table)).columns}
    if target not in cols:
        raise ValueError(f"target '{target}' is not a column of {table}. "
                         f"Columns: {sorted(cols)}")

    limit = f" LIMIT {a.max_rows}" if a.max_rows else ""
    rows = con.run(f"SELECT * FROM {table}{limit}",
                   purpose="pre-model redundancy check").rows
    plan = FeaturePlan(table=table, target=target, entity=entity,
                       numeric=numeric, categorical=categorical)
    features = sorted(numeric + categorical)

    determ, dupes = check_pairs(rows, sorted(categorical), sorted(numeric))
    rank, ncol, offenders = check_rank(rows, plan)
    sep = check_separation(rows, plan)

    out = [f"# redundancy check — {a.source}.{table} (target={target}, n={len(rows)})",
           f"features: {len(features)} ({len(numeric)} numeric, "
           f"{len(categorical)} categorical)", ""]
    out.append("## 1-2. functional determinism / duplicates")
    for x, y, n in dupes:
        out.append(f"  DUPLICATE  {x} <-> {y} (relabelling, {n} levels) — keep one")
    for x, y, nx, ny in determ:
        out.append(f"  DETERMINES {x} ({nx}) -> {y} ({ny}) — drop the coarser column {y}")
    if not dupes and not determ:
        out.append("  clean")
    out += ["", "## 3. design-matrix rank",
            f"  rank {rank} / {ncol} columns" + ("" if rank == ncol else "  DEFICIENT")]
    for col, ndep, nblock, examples, partners in offenders:
        shown = ", ".join(partners[:4]) + ("  (+ more — a multi-column combination)"
                                           if len(partners) > 4 else "")
        out.append(f"  {col}: {ndep} of {nblock} encoded column(s) are an exact linear "
                   f"combination of earlier columns "
                   f"[{', '.join(examples)}{'...' if ndep > len(examples) else ''}]")
        out.append(f"      entangled with: {shown or 'the intercept (constant column)'}"
                   f" — drop ONE side of that pair (keep the more interpretable column)")
    out += ["", "## 4. quasi-separation screen"]
    for c, lv, n in sep:
        out.append(f"  {c}: target is constant on level(s) [{lv}] covering {n} rows — "
                   f"the fit will diverge; exclude unless it is a genuine driver")
    if not sep:
        out.append("  clean")

    # Rank deficiency alone is a failure even when no single block explains it.
    failed = bool(dupes or determ or sep or rank < ncol)
    out += ["", "VERDICT: " + ("REDUNDANCY FOUND — do not fit yet" if failed
                               else "clean — safe to fit")]
    if not a.quiet:
        print("\n".join(out))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a broken check must not read as an all-clear
        print(f"redundancy_check ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
