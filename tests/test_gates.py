from atlas.lib.budget import RunBudget, BudgetBreach
from atlas.lib.gates import (
    Defect,
    GateStatus,
    ReworkTracker,
    gate1_profiling,
    gate2_semantics,
    gate3_redteam,
    gate4_provenance,
    gate5_stakeholder,
)


def test_gate1_needs_one_go():
    assert gate1_profiling({"a": "GO", "b": "NO-GO"}).passed
    assert not gate1_profiling({"a": "NO-GO"}).passed


def test_gate2_unresolved_routes_to_semantic_architect():
    r = gate2_semantics(["margin"])
    assert not r.passed
    assert r.defects[0].owner == "semantic-architect"


def test_gate3_redteam_veto():
    assert gate3_redteam(True, []).passed
    r = gate3_redteam(False, ["filter leakage on region"])
    assert not r.passed
    kinds = {d.kind for d in r.defects}
    assert "failed_rederivation" in kinds
    assert "weak_causal_logic" in kinds


def test_gate4_orphan_number_blocks_and_routes():
    r = gate4_provenance(["c7"])
    assert not r.passed
    assert r.defects[0].owner == "sql-engineer"


def test_gate5_unanswered_routes_to_narrative():
    r = gate5_stakeholder(["Why not FX?"])
    assert r.defects[0].owner == "narrative-writer"


def test_rework_escalates_after_cap():
    tr = ReworkTracker()
    d = Defect("unsupported_claim", "x")  # cap 2
    assert tr.register("G", d) == GateStatus.FAIL   # attempt 1
    assert tr.register("G", d) == GateStatus.FAIL   # attempt 2
    assert tr.register("G", d) == GateStatus.ESCALATE  # attempt 3 > cap


def test_metric_ambiguity_cap_is_one():
    tr = ReworkTracker()
    d = Defect("metric_ambiguity", "margin")  # cap 1
    assert tr.register("G2", d) == GateStatus.FAIL
    assert tr.register("G2", d) == GateStatus.ESCALATE


def test_budget_query_cap():
    b = RunBudget(max_queries=2, max_bytes_scanned=10**9, max_wallclock_s=999)
    b.charge_query()
    b.charge_query()
    try:
        b.charge_query()
        assert False, "expected breach"
    except BudgetBreach:
        pass


def test_budget_bytes_cap():
    b = RunBudget(max_queries=99, max_bytes_scanned=100, max_wallclock_s=999)
    try:
        b.charge_query(bytes_scanned=101)
        assert False
    except BudgetBreach:
        pass
