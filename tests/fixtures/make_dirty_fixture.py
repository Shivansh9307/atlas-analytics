"""Deterministic 'dirty' fixture exercising the data-quality repair modules.

Engineered known-answer defects (11 rows = 10 distinct + 1 full duplicate):
  - order_date : ISO text (not DATE)              -> date_repair
  - region     : NULL for USA/Canada rows          -> region_repair (recoverable=3)
  - country    : 'uk','usa' non-canonical spellings -> country_standardisation (2)
  - active     : yes/no/Y/N boolean-as-text         -> boolean_repair
  - category   : 'Gold ' trailing ws; 'gold' vs 'Gold' -> whitespace + case_standardisation
  - quarter    : row 'Sep' mislabelled Q4 (fiscal)  -> quarter_repair (calendar mismatch)
  - month      : correct %b for every row           -> month_repair does NOT fire
  - notes      : ~91% NULL                           -> null_classification (structural)
  - a full duplicate of the last row                -> duplicate_detection

Written as .xlsx (like Sales.xlsx) so pandas preserves object/text columns.
Run: python tests/fixtures/make_dirty_fixture.py  ->  tests/fixtures/dirty.xlsx
"""
from __future__ import annotations

import os

import pandas as pd

# (id, order_date, region, country, active, category, month, quarter, notes)
ROWS = [
    (1,  "2024-01-15", "EMEA", "France",    "yes", "Gold",   "Jan", "Q1", None),
    (2,  "2024-02-20", "APAC", "India",     "no",  "Silver", "Feb", "Q1", None),
    (3,  "2024-03-10", None,   "USA",       "Y",   "gold",   "Mar", "Q1", None),
    (4,  "2024-04-05", None,   "Canada",    "N",   "Silver", "Apr", "Q2", None),
    (5,  "2024-05-12", "EMEA", "uk",        "yes", "Gold ",  "May", "Q2", "n1"),
    (6,  "2024-06-18", "APAC", "Singapore", "no",  "Bronze", "Jun", "Q2", None),
    (7,  "2024-07-22", None,   "usa",       "Y",   "Bronze", "Jul", "Q3", None),
    (8,  "2024-08-30", "EMEA", "Germany",   "N",   "Silver", "Aug", "Q3", None),
    (9,  "2024-09-14", "APAC", "Australia", "yes", "gold",   "Sep", "Q4", None),  # fiscal Q4
    (10, "2024-10-25", "EMEA", "France",    "no",  "Silver", "Oct", "Q4", None),
]
COLS = ["id", "order_date", "region", "country", "active", "category", "month", "quarter", "notes"]


def build() -> pd.DataFrame:
    df = pd.DataFrame(ROWS, columns=COLS)
    df = pd.concat([df, df.iloc[[-1]]], ignore_index=True)  # append a full duplicate
    # Force text columns to object dtype so the Excel round-trip stays text.
    for c in ("order_date", "region", "country", "active", "category", "month", "quarter", "notes"):
        df[c] = df[c].astype("object")
    return df


def main() -> None:
    out = os.path.join(os.path.dirname(__file__), "dirty.xlsx")
    build().to_excel(out, index=False, sheet_name="dirty")
    print(f"wrote {out} (11 rows)")


if __name__ == "__main__":
    main()
