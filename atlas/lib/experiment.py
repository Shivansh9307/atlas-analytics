"""Experiment design — A/B sample size, power, guardrails, decision rules.

Reuses the normal-quantile helpers in stats.py. Deterministic and honest: it reports
the sample size the test actually needs and pairs the success metric with a guardrail
so a "win" that quietly breaks something else is caught.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from atlas.lib.stats import _z_for_conf


@dataclass
class ExperimentDesign:
    baseline_rate: float
    mde_abs: float                 # absolute pct-point effect to detect
    alpha: float
    power: float
    n_per_arm: int
    total_n: int
    guardrails: list[str] = field(default_factory=list)
    decision_rule: str = ""

    def as_dict(self) -> dict:
        return {
            "baseline_rate": self.baseline_rate, "mde_abs": self.mde_abs,
            "alpha": self.alpha, "power": self.power,
            "n_per_arm": self.n_per_arm, "total_n": self.total_n,
            "guardrails": self.guardrails, "decision_rule": self.decision_rule,
        }


def sample_size(baseline_rate: float, mde_abs: float, *,
                power: float = 0.8, alpha: float = 0.05) -> int:
    """Per-arm sample size for a two-proportion test (two-sided).

    n = (z_{1-a/2} + z_{power})^2 * 2 p (1-p) / mde^2, rounded up.
    """
    if not (0 < baseline_rate < 1) or mde_abs <= 0:
        raise ValueError("baseline_rate in (0,1) and mde_abs > 0 required")
    z_a = _z_for_conf(1 - alpha / 2)
    z_b = _z_for_conf(power)
    p = baseline_rate
    n = (z_a + z_b) ** 2 * 2 * p * (1 - p) / (mde_abs ** 2)
    return math.ceil(n)


def power_at(n_per_arm: int, baseline_rate: float, mde_abs: float,
             *, alpha: float = 0.05) -> float:
    """Achieved power for a given per-arm n (two-proportion, two-sided)."""
    if n_per_arm <= 0 or not (0 < baseline_rate < 1):
        return 0.0
    p = baseline_rate
    se = math.sqrt(2 * p * (1 - p) / n_per_arm)
    z_a = _z_for_conf(1 - alpha / 2)
    z = mde_abs / se - z_a
    return round(_norm_cdf(z), 4)


def design_experiment(
    baseline_rate: float, mde_abs: float, *, power: float = 0.8, alpha: float = 0.05,
    primary_metric: str = "conversion", guardrail_metrics: list[str] | None = None,
) -> ExperimentDesign:
    n = sample_size(baseline_rate, mde_abs, power=power, alpha=alpha)
    guardrails = guardrail_metrics or _default_guardrails(primary_metric)
    rule = (f"Ship if the {primary_metric} lift is significant at α={alpha} "
            f"(one test, no peeking) AND no guardrail {guardrails} regresses beyond "
            f"its pre-registered threshold. Otherwise hold.")
    return ExperimentDesign(
        baseline_rate=baseline_rate, mde_abs=mde_abs, alpha=alpha, power=power,
        n_per_arm=n, total_n=2 * n, guardrails=guardrails, decision_rule=rule)


def _default_guardrails(primary: str) -> list[str]:
    table = {
        "conversion": ["revenue_per_session", "refund_rate"],
        "signup": ["activation_rate", "spam_rate"],
        "checkout": ["aov", "support_tickets"],
    }
    return table.get(primary, ["revenue", "complaint_rate"])


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))
