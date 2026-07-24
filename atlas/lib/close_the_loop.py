"""Close-the-loop: every recommendation gets an owner, a success metric paired with
a GUARDRAIL, a follow-up date, and a fallback. A recommendation without these is a
wish, not a plan — and a success metric without a guardrail invites a win that
quietly breaks something else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from atlas.lib.experiment import _default_guardrails


@dataclass
class Recommendation:
    action: str
    decision_owner: str
    success_metric: str
    guardrail_metric: str = ""
    follow_up: str = ""            # ISO date
    fallback: str = ""

    def __post_init__(self):
        if not self.guardrail_metric:
            g = _default_guardrails(self.success_metric)
            self.guardrail_metric = g[0] if g else "complaint_rate"
        if not self.follow_up:
            self.follow_up = (date.today() + timedelta(days=30)).isoformat()

    def missing_fields(self) -> list[str]:
        req = {"action": self.action, "decision_owner": self.decision_owner,
               "success_metric": self.success_metric,
               "guardrail_metric": self.guardrail_metric,
               "follow_up": self.follow_up, "fallback": self.fallback}
        return [k for k, v in req.items() if not v]

    @property
    def complete(self) -> bool:
        return not self.missing_fields()

    def render(self) -> str:
        return (f"- **{self.action}**\n"
                f"  - Owner: {self.decision_owner}\n"
                f"  - Success metric: {self.success_metric} "
                f"(guardrail: {self.guardrail_metric})\n"
                f"  - Follow-up: {self.follow_up}\n"
                f"  - Fallback: {self.fallback}")


def close_the_loop(recs: list[Recommendation]) -> dict:
    """Validate a set of recommendations; flag any that aren't a real plan."""
    incomplete = {r.action: r.missing_fields() for r in recs if not r.complete}
    return {
        "complete": not incomplete,
        "incomplete": incomplete,
        "rendered": "\n".join(r.render() for r in recs),
    }
