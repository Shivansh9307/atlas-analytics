"""Structured decomposition — the maths that turns "vibes" into contribution.

Provides:
  * decompose_margin  — exact mix / rate / interaction split of a ratio metric
                        (e.g. gross margin) between two periods.
  * additive_contribution — for additive metrics (revenue, cost): each segment's
                        signed contribution to the total delta.
  * simpsons_check    — flags when an aggregate moves opposite to every segment.

All functions are deterministic and return numbers only — never prose. Numbers
they emit must still be provenance-stamped by the caller against stored queries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class SegmentContribution:
    key: str
    mix: float          # contribution from weight shift (rate held at period-1)
    rate: float         # contribution from within-segment margin change
    interaction: float  # residual cross term
    w1: float
    w2: float
    m1: float
    m2: float

    @property
    def total(self) -> float:
        return self.mix + self.rate + self.interaction


@dataclass
class MarginDecomposition:
    m1: float                 # period-1 portfolio margin (fraction)
    m2: float                 # period-2 portfolio margin (fraction)
    delta: float              # m2 - m1 (fraction; multiply by 100 for pts)
    mix_total: float
    rate_total: float
    interaction_total: float
    segments: list[SegmentContribution] = field(default_factory=list)

    @property
    def delta_pts(self) -> float:
        return self.delta * 100.0

    def dominant_effect(self) -> str:
        mags = {"mix": abs(self.mix_total), "rate": abs(self.rate_total),
                "interaction": abs(self.interaction_total)}
        return max(mags, key=mags.get)

    def as_dict(self) -> dict:
        return {
            "m1_pct": round(self.m1 * 100, 4),
            "m2_pct": round(self.m2 * 100, 4),
            "delta_pts": round(self.delta_pts, 4),
            "mix_pts": round(self.mix_total * 100, 4),
            "rate_pts": round(self.rate_total * 100, 4),
            "interaction_pts": round(self.interaction_total * 100, 4),
            "dominant": self.dominant_effect(),
            "segments": [
                {"key": s.key, "mix_pts": round(s.mix * 100, 4),
                 "rate_pts": round(s.rate * 100, 4),
                 "interaction_pts": round(s.interaction * 100, 4),
                 "total_pts": round(s.total * 100, 4)}
                for s in self.segments
            ],
        }


def _agg(rows: Iterable[dict], dim: str, rev_key: str, cogs_key: str):
    """Aggregate revenue and profit by dimension value."""
    rev: dict[str, float] = {}
    profit: dict[str, float] = {}
    for r in rows:
        k = str(r[dim])
        rv = float(r[rev_key])
        cg = float(r[cogs_key])
        rev[k] = rev.get(k, 0.0) + rv
        profit[k] = profit.get(k, 0.0) + (rv - cg)
    return rev, profit


def decompose_margin(
    period1: Iterable[dict],
    period2: Iterable[dict],
    dim: str,
    *,
    rev_key: str = "revenue",
    cogs_key: str = "cogs",
) -> MarginDecomposition:
    """Exact mix/rate/interaction decomposition of margin change between periods.

    Portfolio margin M = Σ_i w_i * m_i, where
        w_i = rev_i / Σ rev   (mix weight)
        m_i = profit_i / rev_i (segment margin)

    ΔM = Σ_i [ (w2_i - w1_i)·m1_i        # MIX  (holding rate at period 1)
             +  w1_i·(m2_i - m1_i)        # RATE (holding mix at period 1)
             + (w2_i - w1_i)(m2_i - m1_i) # INTERACTION (residual) ]
    This identity is exact: mix+rate+interaction == ΔM.
    """
    rev1, profit1 = _agg(period1, dim, rev_key, cogs_key)
    rev2, profit2 = _agg(period2, dim, rev_key, cogs_key)

    tot1 = sum(rev1.values())
    tot2 = sum(rev2.values())
    if tot1 == 0 or tot2 == 0:
        raise ValueError("zero total revenue in a period; cannot compute margin")

    m1 = sum(profit1.values()) / tot1
    m2 = sum(profit2.values()) / tot2

    keys = sorted(set(rev1) | set(rev2))
    segs: list[SegmentContribution] = []
    mix_t = rate_t = inter_t = 0.0
    for k in keys:
        r1, r2 = rev1.get(k, 0.0), rev2.get(k, 0.0)
        w1 = r1 / tot1
        w2 = r2 / tot2
        # segment margins; if a segment is absent in a period its margin is 0
        sm1 = (profit1.get(k, 0.0) / r1) if r1 else 0.0
        sm2 = (profit2.get(k, 0.0) / r2) if r2 else 0.0
        mix = (w2 - w1) * sm1
        rate = w1 * (sm2 - sm1)
        inter = (w2 - w1) * (sm2 - sm1)
        mix_t += mix
        rate_t += rate
        inter_t += inter
        segs.append(SegmentContribution(k, mix, rate, inter, w1, w2, sm1, sm2))

    segs.sort(key=lambda s: abs(s.total), reverse=True)
    return MarginDecomposition(
        m1=m1, m2=m2, delta=m2 - m1,
        mix_total=mix_t, rate_total=rate_t, interaction_total=inter_t,
        segments=segs,
    )


def additive_contribution(
    period1: Iterable[dict],
    period2: Iterable[dict],
    dim: str,
    value_key: str,
) -> list[dict]:
    """Signed contribution of each segment to the total delta of an ADDITIVE metric.

    Returns rows sorted by |contribution| desc, each with share of total delta.
    """
    a: dict[str, float] = {}
    b: dict[str, float] = {}
    for r in period1:
        a[str(r[dim])] = a.get(str(r[dim]), 0.0) + float(r[value_key])
    for r in period2:
        b[str(r[dim])] = b.get(str(r[dim]), 0.0) + float(r[value_key])
    total_delta = sum(b.values()) - sum(a.values())
    out = []
    for k in sorted(set(a) | set(b)):
        contrib = b.get(k, 0.0) - a.get(k, 0.0)
        out.append({
            "key": k,
            "period1": a.get(k, 0.0),
            "period2": b.get(k, 0.0),
            "contribution": contrib,
            "share_of_delta": (contrib / total_delta) if total_delta else None,
        })
    out.sort(key=lambda d: abs(d["contribution"]), reverse=True)
    return out


def simpsons_check(
    period1: Iterable[dict],
    period2: Iterable[dict],
    dim: str,
    *,
    rev_key: str = "revenue",
    cogs_key: str = "cogs",
) -> dict:
    """Flag Simpson's paradox: aggregate margin moves opposite to EVERY segment.

    Returns {paradox: bool, aggregate_delta_pts, segment_deltas_pts}.
    """
    rev1, profit1 = _agg(period1, dim, rev_key, cogs_key)
    rev2, profit2 = _agg(period2, dim, rev_key, cogs_key)
    agg1 = sum(profit1.values()) / sum(rev1.values())
    agg2 = sum(profit2.values()) / sum(rev2.values())
    agg_delta = (agg2 - agg1) * 100

    seg_deltas = {}
    for k in sorted(set(rev1) & set(rev2)):
        if rev1[k] and rev2[k]:
            sm1 = profit1[k] / rev1[k]
            sm2 = profit2[k] / rev2[k]
            seg_deltas[k] = round((sm2 - sm1) * 100, 4)

    signs = {(-1 if d < 0 else 1 if d > 0 else 0) for d in seg_deltas.values() if d != 0}
    agg_sign = -1 if agg_delta < 0 else 1 if agg_delta > 0 else 0
    paradox = bool(seg_deltas) and signs == {-agg_sign} and agg_sign != 0

    return {
        "paradox": paradox,
        "aggregate_delta_pts": round(agg_delta, 4),
        "segment_deltas_pts": seg_deltas,
    }
