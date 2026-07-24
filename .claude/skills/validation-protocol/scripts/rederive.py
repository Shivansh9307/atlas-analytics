#!/usr/bin/env python3
"""Independent re-derivation of a headline gross margin from raw sums.

Usage: rederive.py <source> <region> <p1> <p2> <headline_p1_pct> <headline_p2_pct>
Exits 0 if both re-derivations land within TOLERANCES.rederivation_rel.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from atlas.config import TOLERANCES
from atlas.connectors.registry import Registry


def main() -> int:
    if len(sys.argv) != 7:
        print(__doc__)
        return 2
    source, region, p1, p2, h1, h2 = sys.argv[1:7]
    h1, h2 = float(h1), float(h2)
    con = Registry().connector(source)
    tbl = con.table_name
    res = con.run(
        f"SELECT quarter, sum(revenue) AS rev, sum(cogs) AS cogs FROM {tbl} "
        f"WHERE region = '{region}' AND quarter IN ('{p1}','{p2}') GROUP BY quarter"
    )
    by = {r["quarter"]: (r["rev"], r["cogs"]) for r in res.rows}
    m1 = (by[p1][0] - by[p1][1]) / by[p1][0] * 100
    m2 = (by[p2][0] - by[p2][1]) / by[p2][0] * 100
    tol = TOLERANCES.rederivation_rel
    ok1 = abs(m1 - h1) <= abs(h1) * tol
    ok2 = abs(m2 - h2) <= abs(h2) * tol
    print(f"{p1}: rederived={m1:.4f}% headline={h1:.4f}% -> {'OK' if ok1 else 'MISMATCH'}")
    print(f"{p2}: rederived={m2:.4f}% headline={h2:.4f}% -> {'OK' if ok2 else 'MISMATCH'}")
    print(f"tolerance=±{tol*100:.2f}% relative -> {'PASS' if ok1 and ok2 else 'FAIL'}")
    con.close()
    return 0 if ok1 and ok2 else 1


if __name__ == "__main__":
    sys.exit(main())
