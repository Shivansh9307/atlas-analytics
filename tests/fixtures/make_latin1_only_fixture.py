"""Deterministic fixture that exhausts the cp1252 attempt and lands on latin-1.

`_register_csv_non_utf8()` tries ("cp1252", "latin-1") in order. Byte 0x81 is a
genuine gap in cp1252 (undefined codepoint, `bytes([0x81]).decode("cp1252")`
raises `UnicodeDecodeError`) but decodes cleanly under latin-1 (every byte 0-255
is a valid latin-1 codepoint). It is also, on its own, an invalid UTF-8 byte
(a continuation byte with no lead byte), so DuckDB's reader rejects the file
the same way it rejects a cp1252 export — this fixture exercises the SECOND
loop iteration specifically, which the cp1252 fixture never reaches.

Known-answer design (2 rows, id/tag):
  1  tag holds the raw 0x81 byte — the row this fixture exists to force
  2  plain ASCII control row — proves the fallback doesn't mangle unaffected rows

Run: python tests/fixtures/make_latin1_only_fixture.py -> tests/fixtures/latin1_only.csv
"""
from __future__ import annotations

import os


def build_bytes() -> bytes:
    lines = [b"id,tag\r\n"]
    lines.append(b"1,x" + bytes([0x81]) + b"y\r\n")
    lines.append(b"2,plain\r\n")
    return b"".join(lines)


def main() -> None:
    out = os.path.join(os.path.dirname(__file__), "latin1_only.csv")
    with open(out, "wb") as f:
        f.write(build_bytes())
    print(f"wrote {out} (2 rows, forces latin-1 fallback)")


if __name__ == "__main__":
    main()
