#!/usr/bin/env python3
"""CLI wrapper over atlas.lib.decomposition for ad-hoc mix/rate analysis.

Usage: decompose.py <source> <region> <p1> <p2> [dim]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from atlas.connectors.registry import Registry
from atlas.lib.decomposition import decompose_margin, simpsons_check


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__)
        return 2
    source, region, p1, p2 = sys.argv[1:5]
    dim = sys.argv[5] if len(sys.argv) > 5 else "product_line"
    con = Registry().connector(source)
    tbl = con.table_name

    def rows(q):
        return con.run(
            f"SELECT {dim}, segment, revenue, cogs FROM {tbl} "
            f"WHERE region = '{region}' AND quarter = '{q}'"
        ).rows

    dec = decompose_margin(rows(p1), rows(p2), dim=dim)
    out = dec.as_dict()
    out["simpson"] = simpsons_check(rows(p1), rows(p2), dim=dim)
    print(json.dumps(out, indent=2))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
