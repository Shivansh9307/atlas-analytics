"""4-layer validation stack + an A–F confidence grade.

Complements the red-team's independent re-derivation with a structured, gradable
verdict:
  L1 structural  — schema / keys / completeness present
  L2 logical     — aggregation consistency, trend/sign logic
  L3 business    — plausibility vs known ranges & business rules
  L4 Simpson     — no aggregate-vs-segment reversal hiding

The grade is *advisory* — it never overrides the red-team veto (Gate 3). A grade of F
adds one surviving attack; otherwise it annotates confidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LayerResult:
    layer: str                 # structural | logical | business | simpson
    passed: bool
    weight: float = 1.0
    detail: str = ""


@dataclass
class ValidationReport:
    layers: list[LayerResult]
    grade: str
    score: float

    @property
    def confident(self) -> bool:
        return self.grade in ("A", "B")

    def as_dict(self) -> dict:
        return {
            "grade": self.grade, "score": round(self.score, 3),
            "layers": [{"layer": l.layer, "passed": l.passed, "detail": l.detail}
                       for l in self.layers],
        }


def _grade(score: float) -> str:
    if score >= 0.95:
        return "A"
    if score >= 0.85:
        return "B"
    if score >= 0.70:
        return "C"
    if score >= 0.50:
        return "D"
    return "F"


def grade_layers(layers: list[LayerResult]) -> ValidationReport:
    total_w = sum(l.weight for l in layers) or 1.0
    score = sum(l.weight for l in layers if l.passed) / total_w
    return ValidationReport(layers=layers, grade=_grade(score), score=score)


# --- layer builders for the margin pipeline (deterministic, structured inputs) ---

def structural_layer(row_count: int, profile_ok: bool) -> LayerResult:
    ok = row_count > 0 and profile_ok
    return LayerResult("structural", ok, weight=1.0,
                       detail=f"rows={row_count}, profile_ok={profile_ok}")


def logical_layer(mix: float, rate: float, interaction: float, delta: float,
                  *, tol: float = 1e-6) -> LayerResult:
    """The decomposition identity must hold: mix + rate + interaction == delta."""
    ok = abs((mix + rate + interaction) - delta) <= tol
    return LayerResult("logical", ok, weight=1.5,
                       detail=f"mix+rate+interaction={mix+rate+interaction:.6f} vs Δ={delta:.6f}")


def business_layer(m1: float, m2: float, *, lo: float = 0.0, hi: float = 1.0) -> LayerResult:
    """Margins must be plausible (within [lo, hi])."""
    ok = lo <= m1 <= hi and lo <= m2 <= hi
    return LayerResult("business", ok, weight=1.0,
                       detail=f"m1={m1:.4f}, m2={m2:.4f} in [{lo},{hi}]")


def simpson_layer(paradox: bool) -> LayerResult:
    return LayerResult("simpson", not paradox, weight=1.0,
                       detail="paradox flagged" if paradox else "no paradox")


def validate_margin_finding(*, row_count: int, profile_ok: bool,
                            mix: float, rate: float, interaction: float, delta: float,
                            m1: float, m2: float, paradox: bool) -> ValidationReport:
    """Convenience: run all four layers for a margin decomposition finding."""
    return grade_layers([
        structural_layer(row_count, profile_ok),
        logical_layer(mix, rate, interaction, delta),
        business_layer(m1, m2),
        simpson_layer(paradox),
    ])
