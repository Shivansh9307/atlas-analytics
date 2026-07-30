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


# --- generic layers, for playbooks whose finding is not a margin identity ---
# `logical_layer` above asserts mix+rate+interaction == delta, which only a
# decomposition has. These are its analogues for a ranked-driver finding.

def identity_layer(parts: dict[str, float], total: float, *, tol: float = 1e-6,
                   name: str = "identity") -> LayerResult:
    """An accounting identity: the parts must reconstitute the whole.

    For a driver ranking the identity is the law of total probability — the
    size-weighted average of the per-segment rates must equal the overall rate. If it
    does not, the grouping dropped or double-counted rows.
    """
    got = sum(parts.values())
    ok = abs(got - total) <= tol
    return LayerResult(name, ok, weight=1.5,
                       detail=f"sum(parts)={got:.6f} vs total={total:.6f} (tol {tol})")


def range_layer(values: dict[str, float], lo: float = 0.0, hi: float = 1.0
                ) -> LayerResult:
    """Every named value sits inside a plausible range (rates in [0,1], etc.)."""
    bad = {k: v for k, v in values.items() if v is None or not (lo <= v <= hi)}
    return LayerResult("business_range", not bad, weight=1.0,
                       detail=("all in range" if not bad else f"out of [{lo},{hi}]: {bad}"))


def sample_size_layer(n: int, *, minimum: int = 384) -> LayerResult:
    """Enough rows for a ±5% margin at 95% confidence (the usual 384 rule of thumb)."""
    return LayerResult("sample_size", n >= minimum, weight=1.0,
                       detail=f"n={n} (minimum {minimum})")


def effect_significance_layer(significant: bool | None, effect: float,
                              *, min_effect: float = 0.0) -> LayerResult:
    """The headline driver is both statistically and materially distinguishable."""
    ok = bool(significant) and abs(effect) > min_effect
    return LayerResult("top_effect", ok, weight=1.0,
                       detail=f"significant={significant}, |effect|={abs(effect):.4f}")


def validate_ranked_findings(*, row_count: int, profile_ok: bool,
                             weighted_parts: dict[str, float], overall_rate: float,
                             rates: dict[str, float],
                             top_significant: bool | None, top_effect: float,
                             tol: float = 1e-6) -> ValidationReport:
    """The ranked-driver analogue of `validate_margin_finding`."""
    return grade_layers([
        structural_layer(row_count, profile_ok),
        identity_layer(weighted_parts, overall_rate, tol=tol, name="rate_identity"),
        range_layer(rates),
        sample_size_layer(row_count),
        effect_significance_layer(top_significant, top_effect),
    ])
