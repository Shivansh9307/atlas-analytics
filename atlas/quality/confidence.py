"""Multi-level confidence: roll up the whole chain of trust into one number.

Overall confidence is a chain: a strong narrative on a weak metric definition, or
on low-quality data, is not trustworthy. So the roll-up is dragged toward its
WEAKEST link (blends the weighted mean with the minimum), extending the 4-layer
validator rather than replacing it.

Components (spec 'Multi-Level Confidence'):
  data_quality · metric_definition · statistics · business_logic · narrative
"""
from __future__ import annotations

from dataclasses import dataclass

_GRADE_TO_SCORE = {"A": 0.95, "B": 0.85, "C": 0.70, "D": 0.50, "F": 0.30}
_WEIGHTS = {"data_quality": 0.30, "metric_definition": 0.20, "statistics": 0.20,
            "business_logic": 0.15, "narrative": 0.15}
_BANDS = [(0.90, "Very High"), (0.75, "High"), (0.60, "Moderate"), (0.40, "Low")]


def grade_score(grade: str) -> float:
    return _GRADE_TO_SCORE.get((grade or "").upper(), 0.5)


@dataclass
class MultiLevelConfidence:
    components: dict[str, float]
    overall: float
    band: str
    weakest: str

    def as_dict(self) -> dict:
        return {"components": {k: round(v, 3) for k, v in self.components.items()},
                "overall": round(self.overall, 3), "band": self.band, "weakest": self.weakest}


def _band(x: float) -> str:
    for cut, label in _BANDS:
        if x >= cut:
            return label
    return "Very Low"


def overall_confidence(*, data_quality: float, metric_definition: float,
                       statistics: float, business_logic: float,
                       narrative: float) -> MultiLevelConfidence:
    comp = {"data_quality": data_quality, "metric_definition": metric_definition,
            "statistics": statistics, "business_logic": business_logic,
            "narrative": narrative}
    comp = {k: max(0.0, min(1.0, v)) for k, v in comp.items()}
    wmean = sum(comp[k] * w for k, w in _WEIGHTS.items())
    weakest_k = min(comp, key=comp.get)
    # chain of trust: pulled toward the weakest link
    overall = round(0.6 * wmean + 0.4 * comp[weakest_k], 3)
    return MultiLevelConfidence(components=comp, overall=overall,
                                band=_band(overall), weakest=weakest_k)


def render(mlc: MultiLevelConfidence) -> str:
    lines = ["# Multi-level confidence", "", "| level | score |", "|---|---|"]
    for k, v in mlc.components.items():
        lines.append(f"| {k} | {v:.2f} |")
    lines += ["", f"**Overall:** {mlc.overall:.2f} ({mlc.band}) — "
              f"weakest link: **{mlc.weakest}**."]
    return "\n".join(lines)
