"""Executive recommendations + interactive next-best-actions.

Every analysis ends with a decision-grade close (spec 'Executive Recommendations'):
Root Cause · Business Recommendation · Estimated Impact · Confidence · Next Best
Actions — and an interactive offer of follow-on work.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Interactive-conversation menu (spec 'Interactive Conversation').
FOLLOW_UP_OFFERS = [
    "a Power BI / dashboard build",
    "customer segmentation",
    "a forecast of the metric",
    "scenario / what-if modelling",
    "an executive one-paragraph summary",
]


@dataclass
class ExecRecommendation:
    root_cause: str
    recommendation: str
    estimated_impact: str
    confidence: str
    next_best_actions: list[str] = field(default_factory=list)
    follow_up_offers: list[str] = field(default_factory=lambda: list(FOLLOW_UP_OFFERS))

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def next_best_actions(*, level: int, pending_approvals: list[str] | None = None,
                      has_forecast: bool = False) -> list[str]:
    actions: list[str] = []
    if pending_approvals:
        actions.append(f"Approve pending repair(s) {pending_approvals} via `/clean <source> --apply` "
                       f"to lift data confidence.")
    if level == 3:
        actions.append("Instrument the identified driver as a weekly leading indicator.")
    if not has_forecast:
        actions.append("Forecast the metric forward with `/forecast` to pre-empt recurrence.")
    actions.append("Design an A/B test with `/experiment` before committing spend.")
    return actions


def executive_recommendation(*, root_cause: str, recommendation: str,
                             estimated_impact: str, confidence: str,
                             level: int = 3, pending_approvals: list[str] | None = None,
                             has_forecast: bool = False) -> ExecRecommendation:
    return ExecRecommendation(
        root_cause=root_cause, recommendation=recommendation,
        estimated_impact=estimated_impact, confidence=confidence,
        next_best_actions=next_best_actions(level=level, pending_approvals=pending_approvals,
                                            has_forecast=has_forecast))


def render(rec: ExecRecommendation) -> str:
    return (
        f"# Executive recommendation\n\n"
        f"**Root cause:** {rec.root_cause}\n\n"
        f"**Recommendation:** {rec.recommendation}\n\n"
        f"**Estimated impact:** {rec.estimated_impact}\n\n"
        f"**Confidence:** {rec.confidence}\n\n"
        f"**Next best actions:**\n" + "\n".join(f"- {a}" for a in rec.next_best_actions) +
        f"\n\n**Would you also like:**\n" + "\n".join(f"- {o}" for o in rec.follow_up_offers) + "\n"
    )
