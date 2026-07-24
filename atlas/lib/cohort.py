"""Cohort analysis — retention, vintage comparison, cohort LTV.

Deterministic, operates on plain rows (list[dict]) so it is trivially testable and
never invents data. A "cohort" is a group keyed by first-seen period; "offset" is the
number of periods since the cohort formed (0 = formation period).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetentionMatrix:
    cohorts: list[str]
    offsets: list[int]
    size: dict[str, int]                       # cohort -> users at offset 0
    retained: dict[str, dict[int, int]]        # cohort -> offset -> distinct users
    rate: dict[str, dict[int, float]]          # cohort -> offset -> retention rate

    def as_dict(self) -> dict:
        return {
            "cohorts": self.cohorts, "offsets": self.offsets, "size": self.size,
            "rate": {c: {o: round(r, 4) for o, r in self.rate[c].items()}
                     for c in self.cohorts},
        }

    def overall_rate(self, offset: int) -> float:
        """Weighted retention across cohorts at a given offset."""
        num = sum(self.retained[c].get(offset, 0) for c in self.cohorts)
        den = sum(self.size[c] for c in self.cohorts if offset in self.rate[c])
        return num / den if den else 0.0


def retention_matrix(
    rows: list[dict], *, user_key: str, cohort_key: str, offset_key: str,
) -> RetentionMatrix:
    """Build a cohort × offset retention matrix from activity rows.

    Each row = one (user active in a period). offset is the integer periods since the
    user's cohort formed. Cohort size = distinct users seen at offset 0.
    """
    by_cohort_offset: dict[str, dict[int, set]] = {}
    for r in rows:
        c = str(r[cohort_key])
        o = int(r[offset_key])
        by_cohort_offset.setdefault(c, {}).setdefault(o, set()).add(r[user_key])

    cohorts = sorted(by_cohort_offset)
    offsets = sorted({o for cm in by_cohort_offset.values() for o in cm})
    size: dict[str, int] = {}
    retained: dict[str, dict[int, int]] = {}
    rate: dict[str, dict[int, float]] = {}
    for c in cohorts:
        base = len(by_cohort_offset[c].get(0, set()))
        size[c] = base
        retained[c] = {o: len(by_cohort_offset[c].get(o, set())) for o in offsets
                       if o in by_cohort_offset[c]}
        rate[c] = {o: (retained[c][o] / base if base else 0.0) for o in retained[c]}
    return RetentionMatrix(cohorts, offsets, size, retained, rate)


def cohort_ltv(
    rows: list[dict], *, cohort_key: str, user_key: str, value_key: str, offset_key: str,
) -> dict[str, dict[int, float]]:
    """Cumulative average value per user, by cohort and offset.

    Returns cohort -> offset -> cumulative avg value per formation-period user.
    """
    value: dict[str, dict[int, float]] = {}
    base_users: dict[str, set] = {}
    for r in rows:
        c = str(r[cohort_key])
        o = int(r[offset_key])
        value.setdefault(c, {}).setdefault(o, 0.0)
        value[c][o] += float(r[value_key])
        if o == 0:
            base_users.setdefault(c, set()).add(r[user_key])

    out: dict[str, dict[int, float]] = {}
    for c, per_off in value.items():
        n = len(base_users.get(c, set())) or 1
        cum = 0.0
        out[c] = {}
        for o in sorted(per_off):
            cum += per_off[o]
            out[c][o] = round(cum / n, 4)
    return out


def vintage_compare(matrix: RetentionMatrix, offset: int) -> list[dict]:
    """Rank cohorts by retention at a given offset — spot improving/worsening vintages."""
    out = [{"cohort": c, "rate": round(matrix.rate[c].get(offset, 0.0), 4),
            "size": matrix.size[c]}
           for c in matrix.cohorts if offset in matrix.rate[c]]
    out.sort(key=lambda d: d["rate"], reverse=True)
    return out
