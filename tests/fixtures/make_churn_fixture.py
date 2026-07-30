"""Generate a deterministic churn-shaped fixture for the descriptive/logistic tests.

`data/` is gitignored, so the real churn.csv cannot back the test suite. This plants
the same structure the real file has, at 1/10th the size:

  * a **double cliff** on Payment Delay — flat ~0.10 below 16, ~0.58 for 16-20,
    ~0.77 at 21+ — which is what the threshold detector must find and what a plain
    linear logistic term would underfit
  * a monotone protective effect from Tenure (longer tenure, less churn)
  * a genuine categorical driver (Contract Length)
  * `Gender` deliberately has NO effect, so a "demographic disparity" question has a
    correct negative answer to find
  * `CustomerID` unique, so entity binding has something to bind

Seeded, so the numbers are identical on every machine and the tests can assert exact
cut points.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent / "churn.csv"
N = 6000
SEED = 42

GENDERS = ["Male", "Female"]
SUBS = ["Basic", "Standard", "Premium"]
CONTRACTS = ["Monthly", "Quarterly", "Annual"]
# Contract Length is a real driver; monthly customers churn far more.
CONTRACT_EFFECT = {"Monthly": 0.18, "Quarterly": 0.0, "Annual": -0.15}


def payment_delay_risk(pd_days: int) -> float:
    """The planted staircase — the whole point of this fixture."""
    if pd_days < 16:
        return 0.10
    if pd_days < 21:
        return 0.58
    return 0.77


def build_rows(rng: random.Random) -> list[dict]:
    rows = []
    for cid in range(1, N + 1):
        pd_days = rng.randint(0, 30)
        tenure = rng.randint(1, 60)
        support = rng.randint(0, 10)
        contract = rng.choice(CONTRACTS)

        p = payment_delay_risk(pd_days)
        p += CONTRACT_EFFECT[contract]
        p += -0.0025 * tenure          # gentle monotone protection
        p += 0.012 * support           # gentle monotone risk
        p = min(0.98, max(0.01, p))

        rows.append({
            "CustomerID": cid,
            "Age": rng.randint(18, 65),
            "Gender": rng.choice(GENDERS),          # deliberately inert
            "Tenure": tenure,
            "Usage Frequency": rng.randint(1, 30),  # deliberately inert
            "Support Calls": support,
            "Payment Delay": pd_days,
            "Subscription Type": rng.choice(SUBS),
            "Contract Length": contract,
            "Total Spend": rng.randint(100, 1000),
            "Last Interaction": rng.randint(1, 30),
            "Churn": 1 if rng.random() < p else 0,
        })
    return rows


def main() -> None:
    rng = random.Random(SEED)
    rows = build_rows(rng)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    churned = sum(r["Churn"] for r in rows)
    print(f"wrote {OUT} ({len(rows)} rows, churn rate {churned/len(rows):.4f})")


if __name__ == "__main__":
    main()
