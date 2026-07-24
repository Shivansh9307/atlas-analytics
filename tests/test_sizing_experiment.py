import math

import pytest

from atlas.lib.experiment import (
    design_experiment, power_at, sample_size,
)
from atlas.lib.sizing import (
    Assumption, linear_opportunity_model, size_opportunity,
)


# ---- sizing ----
def test_base_case_and_tornado():
    model = linear_opportunity_model(("volume", "rate_delta", "value_per_unit"))
    a = [
        Assumption("volume", base=1000, low=800, high=1200),
        Assumption("rate_delta", base=0.04, low=0.02, high=0.06),
        Assumption("value_per_unit", base=50, low=50, high=50),   # fixed -> zero swing
    ]
    res = size_opportunity(a, model)
    assert res.base == 1000 * 0.04 * 50                 # 2000
    # rate_delta swings widest (0.02->0.06 on 1000*50) -> most sensitive
    assert res.bars[0].name == "rate_delta"
    assert res.bars[-1].name == "value_per_unit"        # zero swing ranked last
    assert res.bars[-1].swing == 0.0


def test_sizing_as_dict_flags_driver():
    model = linear_opportunity_model()
    res = size_opportunity(
        [Assumption("volume", 100, 50, 150),
         Assumption("rate_delta", 0.1, 0.1, 0.1),
         Assumption("value_per_unit", 10, 10, 10)], model)
    assert res.as_dict()["most_sensitive_to"] == "volume"


# ---- experiment ----
def test_sample_size_matches_formula():
    # baseline 0.10, detect 2pt abs, power .8, alpha .05
    n = sample_size(0.10, 0.02, power=0.8, alpha=0.05)
    # closed-form ~ (1.96+0.8416)^2 * 2*.1*.9 / .02^2 ≈ 3565
    assert 3500 <= n <= 3650


def test_power_rises_with_n():
    lo = power_at(500, 0.10, 0.02)
    hi = power_at(5000, 0.10, 0.02)
    assert hi > lo
    assert 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0


def test_power_at_designed_n_hits_target():
    n = sample_size(0.10, 0.02, power=0.8, alpha=0.05)
    assert abs(power_at(n, 0.10, 0.02) - 0.8) < 0.02     # ~80% by construction


def test_design_includes_guardrails_and_rule():
    d = design_experiment(0.10, 0.02, primary_metric="conversion")
    assert d.n_per_arm > 0 and d.total_n == 2 * d.n_per_arm
    assert d.guardrails                                  # never empty
    assert "guardrail" in d.decision_rule.lower()


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        sample_size(0.0, 0.02)
    with pytest.raises(ValueError):
        sample_size(0.1, 0.0)
