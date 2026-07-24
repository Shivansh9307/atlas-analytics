import time

import pytest

from atlas.dag import (
    DagEngine, DagError, NodeOutcome, NodeSpec, NodeStatus, topological_tiers,
)


# ---- topological tiers ----
def test_tiers_group_independent_nodes():
    specs = [
        NodeSpec("a"), NodeSpec("b"),
        NodeSpec("c", deps=["a", "b"]),
        NodeSpec("d", deps=["c"]),
    ]
    tiers = topological_tiers(specs)
    assert tiers[0] == ["a", "b"]      # independent, same tier
    assert tiers[1] == ["c"]
    assert tiers[2] == ["d"]


def test_unknown_dependency_raises():
    with pytest.raises(DagError):
        topological_tiers([NodeSpec("a", deps=["missing"])])


def test_cycle_raises():
    with pytest.raises(DagError):
        topological_tiers([NodeSpec("a", deps=["b"]), NodeSpec("b", deps=["a"])])


# ---- execution ----
class Ctx:
    def __init__(self):
        self.ran = []
        self.lock = __import__("threading").Lock()

    def mark(self, n):
        with self.lock:
            self.ran.append(n)


def ok(name):
    def fn(ctx):
        ctx.mark(name)
        return NodeOutcome(NodeStatus.OK, output={"node": name})
    return fn


def test_happy_path_runs_all_in_order():
    specs = [NodeSpec("a"), NodeSpec("b", deps=["a"]), NodeSpec("c", deps=["b"])]
    eng = DagEngine(specs)
    ctx = Ctx()
    res = eng.run({"a": ok("a"), "b": ok("b"), "c": ok("c")}, ctx)
    assert res.status == "COMPLETE"
    assert ctx.ran == ["a", "b", "c"]
    assert res.outputs["b"] == {"node": "b"}


def test_parallel_tier_actually_concurrent():
    def slow(name):
        def fn(ctx):
            time.sleep(0.2)
            ctx.mark(name)
            return NodeOutcome(NodeStatus.OK)
        return fn
    specs = [NodeSpec("a"), NodeSpec("b"), NodeSpec("c")]  # all tier 0
    eng = DagEngine(specs, max_concurrency=3)
    t0 = time.monotonic()
    eng.run({"a": slow("a"), "b": slow("b"), "c": slow("c")}, Ctx())
    # 3×0.2s sequential = 0.6s; concurrent should be well under 0.45s
    assert time.monotonic() - t0 < 0.45


def test_blocked_gate_halts_cleanly_no_retry():
    calls = {"n": 0}
    def blocker(ctx):
        calls["n"] += 1
        return NodeOutcome(NodeStatus.BLOCKED, reason="GATE 2: metric ambiguity")
    specs = [NodeSpec("gate", retries=2), NodeSpec("after", deps=["gate"])]
    ctx = Ctx()
    res = DagEngine(specs).run({"gate": blocker, "after": ok("after")}, ctx)
    assert res.status == "BLOCKED"
    assert "GATE 2" in res.reason
    assert calls["n"] == 1                 # BLOCKED is terminal, not retried
    assert "after" not in ctx.ran           # downstream never ran


def test_critical_failure_halts():
    def boom(ctx):
        raise RuntimeError("kaboom")
    specs = [NodeSpec("x", critical=True, retries=0), NodeSpec("y", deps=["x"])]
    res = DagEngine(specs).run({"x": boom, "y": ok("y")}, Ctx())
    assert res.status == "FAILED"
    assert "x" in res.reason


def test_noncritical_failure_degrades_and_skips_dependents():
    def boom(ctx):
        raise RuntimeError("optional down")
    specs = [
        NodeSpec("core"),
        NodeSpec("opt", deps=["core"], critical=False, retries=0),
        NodeSpec("dep_on_opt", deps=["opt"]),
        NodeSpec("dep_on_core", deps=["core"]),
    ]
    ctx = Ctx()
    res = DagEngine(specs, circuit_breaker=99).run(
        {"core": ok("core"), "opt": boom, "dep_on_opt": ok("dep_on_opt"),
         "dep_on_core": ok("dep_on_core")}, ctx)
    assert res.status == "COMPLETE"                 # degraded, not failed
    assert res.node_status["opt"] == "FAILED"
    assert res.node_status["dep_on_opt"] == "SKIPPED"   # its dep failed
    assert res.node_status["dep_on_core"] == "OK"       # unaffected branch ran


def test_timeout_then_retry_succeeds():
    state = {"tries": 0}
    def flaky(ctx):
        state["tries"] += 1
        if state["tries"] == 1:
            time.sleep(0.5)                # first attempt exceeds timeout
        return NodeOutcome(NodeStatus.OK)
    specs = [NodeSpec("f", timeout_s=0.2, retries=1)]
    res = DagEngine(specs).run({"f": flaky}, Ctx())
    assert res.status == "COMPLETE"
    assert state["tries"] == 2


def test_circuit_breaker_trips():
    def boom(ctx):
        raise RuntimeError("x")
    # three independent non-critical failures in one tier
    specs = [NodeSpec(n, critical=False, retries=0) for n in ("a", "b", "c")]
    res = DagEngine(specs, circuit_breaker=3).run(
        {"a": boom, "b": boom, "c": boom}, Ctx())
    assert res.status == "FAILED"
    assert "circuit breaker" in res.reason


def test_resume_skips_completed_nodes():
    specs = [NodeSpec("a"), NodeSpec("b", deps=["a"]), NodeSpec("c", deps=["b"])]
    ctx = Ctx()
    res = DagEngine(specs).run(
        {"a": ok("a"), "b": ok("b"), "c": ok("c")}, ctx,
        completed={"a": {"node": "a"}, "b": {"node": "b"}})
    assert res.status == "COMPLETE"
    assert ctx.ran == ["c"]                 # a, b were skipped/resumed
    assert res.outputs["a"] == {"node": "a"}
