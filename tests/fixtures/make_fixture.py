"""Deterministic generator for the EMEA gross-margin fixture.

Known-answer design (so tests can assert exact decomposition):

  Gross margin = (revenue - cogs) / revenue

  EMEA total GM:  Q1 = 60.0%   Q2 = 56.0%   -> drop of 4.0 pts

  The drop is engineered to be MOSTLY a MIX shift, not a rate shift:
    - Two product lines: "Software" (high margin) and "Hardware" (low margin).
    - Within-line margins (rate) are essentially unchanged Q1->Q2.
    - Revenue mix shifts from Software toward Hardware in Q2.
  A small residual rate effect exists in Hardware so the statistician has
  something real but minor to find.

Run:  python tests/fixtures/make_fixture.py
Produces: tests/fixtures/emea_margin.csv
"""
from __future__ import annotations

import csv
import os

# (region, quarter, product_line, segment, revenue, cogs)
# Revenue/cogs chosen so the aggregates land on clean known numbers.
ROWS: list[tuple[str, str, str, str, float, float]] = []


def add(region, quarter, line, segment, revenue, margin_pct):
    cogs = round(revenue * (1 - margin_pct / 100.0), 2)
    ROWS.append((region, quarter, line, segment, round(revenue, 2), cogs))


# ---- EMEA ----
# Q1: Software 800 @ 70%, Hardware 200 @ 20%  -> total rev 1000
#     GM = (800*.70 + 200*.20)/1000 = (560+40)/1000 = 600/1000 = 60.0%
add("EMEA", "Q1", "Software", "Enterprise", 500, 70.0)
add("EMEA", "Q1", "Software", "SMB",        300, 70.0)
add("EMEA", "Q1", "Hardware", "Enterprise", 120, 20.0)
add("EMEA", "Q1", "Hardware", "SMB",         80, 20.0)

# Q2: Software 500 @ 70%, Hardware 500 @ ~18% -> total rev 1000
#     GM = (500*.70 + 500*.18)/1000 = (350+90)/1000 = 440/1000 = 44.0%? too big.
# Re-tune to hit exactly 56.0%: need (rev-cogs)=560 on rev 1000.
#   Software 600 @ 70% -> profit 420 ; Hardware 400 @ 35% -> profit 140 ; total 560 -> 56.0%
# So mix moved from 80/20 (SW/HW) to 60/40, Hardware rate 20%->... let's keep HW rate ~near.
# Use: Software 600 @ 70% (rate unchanged), Hardware 400 @ 35%? That's a rate RISE, unrealistic.
# Cleaner: hold rates, pure mix. Software 600@70=420, Hardware 400@20=80 -> 500/1000=50%. drop 10pts.
# We want 4pts. So mix shift is milder: Software 720@70=504, Hardware 280@20=56 -> 560/1000=56.0%.
add("EMEA", "Q2", "Software", "Enterprise", 450, 70.0)
add("EMEA", "Q2", "Software", "SMB",        270, 70.0)
add("EMEA", "Q2", "Hardware", "Enterprise", 168, 19.0)  # tiny rate dip (20 -> ~19)
add("EMEA", "Q2", "Hardware", "SMB",        112, 21.5)  # offsetting, blended ~20

# ---- AMER (control region: stable margin ~65% both quarters) ----
add("AMER", "Q1", "Software", "Enterprise", 700, 68.0)
add("AMER", "Q1", "Hardware", "Enterprise", 300, 58.0)
add("AMER", "Q2", "Software", "Enterprise", 710, 68.0)
add("AMER", "Q2", "Hardware", "Enterprise", 290, 58.0)

# ---- APAC (control region: stable ~55%) ----
add("APAC", "Q1", "Software", "SMB", 400, 60.0)
add("APAC", "Q1", "Hardware", "SMB", 200, 45.0)
add("APAC", "Q2", "Software", "SMB", 410, 60.0)
add("APAC", "Q2", "Hardware", "SMB", 205, 45.0)


def main() -> None:
    out = os.path.join(os.path.dirname(__file__), "emea_margin.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["region", "quarter", "product_line", "segment", "revenue", "cogs"])
        for r in ROWS:
            w.writerow(r)
    print(f"wrote {out} ({len(ROWS)} rows)")

    # sanity print of EMEA totals
    for q in ("Q1", "Q2"):
        rev = sum(r[4] for r in ROWS if r[0] == "EMEA" and r[1] == q)
        cogs = sum(r[5] for r in ROWS if r[0] == "EMEA" and r[1] == q)
        print(f"  EMEA {q}: rev={rev:.2f} cogs={cogs:.2f} GM={(rev-cogs)/rev*100:.2f}%")


if __name__ == "__main__":
    main()
