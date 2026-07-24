"""Opportunity sizing with sensitivity (tornado) analysis.

Quantifies the business impact of a finding and — crucially — shows *which
assumptions the number depends on*. A point estimate without a tornado is a guess
with a decimal point; this makes the uncertainty explicit.

Model-agnostic: you supply a `model(assumptions: dict) -> float` and per-assumption
low/base/high ranges. The sizer computes the base case and a ranked tornado.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Assumption:
    name: str
    base: float
    low: float
    high: float


@dataclass
class TornadoBar:
    name: str
    low_output: float
    high_output: float
    base_output: float

    @property
    def swing(self) -> float:
        return abs(self.high_output - self.low_output)


@dataclass
class SizingResult:
    base: float
    bars: list[TornadoBar]

    def as_dict(self) -> dict:
        return {
            "base_case": round(self.base, 4),
            "tornado": [
                {"assumption": b.name, "low": round(b.low_output, 4),
                 "high": round(b.high_output, 4), "swing": round(b.swing, 4)}
                for b in self.bars
            ],
            "most_sensitive_to": self.bars[0].name if self.bars else None,
        }


def size_opportunity(
    assumptions: list[Assumption], model: Callable[[dict], float],
) -> SizingResult:
    """Base-case size + a tornado ranking assumptions by output swing.

    Each bar varies one assumption low->high with the others held at base.
    """
    base_inputs = {a.name: a.base for a in assumptions}
    base = model(base_inputs)

    bars: list[TornadoBar] = []
    for a in assumptions:
        lo = dict(base_inputs, **{a.name: a.low})
        hi = dict(base_inputs, **{a.name: a.high})
        bars.append(TornadoBar(a.name, model(lo), model(hi), base))
    bars.sort(key=lambda b: b.swing, reverse=True)
    return SizingResult(base, bars)


def linear_opportunity_model(keys: tuple[str, ...] = ("volume", "rate_delta", "value_per_unit")):
    """A common sizing shape: impact = product of the given assumption keys.

    e.g. affected_volume × rate_improvement × value_per_unit.
    """
    def model(a: dict) -> float:
        out = 1.0
        for k in keys:
            out *= a[k]
        return out
    return model
