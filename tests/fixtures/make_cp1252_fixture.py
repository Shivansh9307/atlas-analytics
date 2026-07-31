"""Deterministic non-UTF-8 fixture exercising the encoding fallback in csv_duckdb.py.

Windows-1252 exports are the common real-world case: a name/address field with an
accented character or a smart quote, saved by Excel on Windows, lands in DuckDB's
strict UTF-8 reader as an invalid byte sequence. `_register_csv_non_utf8()` retries
via pandas with cp1252 first, then latin-1.

Known-answer design (3 rows, id/name/city):
  1  Mueller has a German umlaut (u-umlaut) and Zurich has one too
  2  contains a curly right-single-quote (0x92 in cp1252) - the classic
     "smart quote from Word" byte that trips DuckDB's reader
  3  plain ASCII control row - proves the fallback doesn't mangle unaffected rows

Written as raw bytes (not via pandas.to_csv) so the exact byte sequence — and
therefore which codec is exercised — is explicit and reviewable.

Run: python tests/fixtures/make_cp1252_fixture.py -> tests/fixtures/cp1252.csv
"""
from __future__ import annotations

import os

ROWS_CP1252 = [
    # (id, name, city) - name/city hold characters only valid once decoded as cp1252
    (1, "Fran\xe7ois M\xfcller", "Z\xfcrich"),      # ç, ü, ü  (0xE7, 0xFC, 0xFC in cp1252)
    (2, "O’Brien", "S\xe3o Paulo"),             # curly ’ (0x92), ã (0xE3) in cp1252
    (3, "Jane Doe", "London"),                        # pure ASCII control row
]


def build_bytes() -> bytes:
    lines = [b"id,name,city\r\n"]
    for row_id, name, city in ROWS_CP1252:
        lines.append(f"{row_id},{name},{city}\r\n".encode("cp1252"))
    return b"".join(lines)


def main() -> None:
    out = os.path.join(os.path.dirname(__file__), "cp1252.csv")
    with open(out, "wb") as f:
        f.write(build_bytes())
    print(f"wrote {out} ({len(ROWS_CP1252)} rows, cp1252-encoded)")


if __name__ == "__main__":
    main()
