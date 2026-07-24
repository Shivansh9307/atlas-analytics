#!/usr/bin/env python3
"""Test a registered source's connection. Usage: conn_test.py <source>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from atlas.connectors.registry import Registry


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    name = sys.argv[1]
    reg = Registry()
    print(f"source '{name}': live={reg.is_live(name)}")
    try:
        con = reg.connector(name)
    except Exception as e:
        print(f"cannot instantiate: {e}")
        return 1
    check = con.test_connection()
    print(f"ok={check.ok} read_only={check.read_only_role} latency_ms={check.latency_ms}")
    print(check.detail)
    con.close()
    return 0 if check.ok else 1


if __name__ == "__main__":
    sys.exit(main())
