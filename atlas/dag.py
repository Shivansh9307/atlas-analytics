"""DAG execution engine.

Turns a node/dependency graph into topologically-ordered execution *tiers* and runs
each tier with bounded parallelism, per-node timeout + one retry, a circuit breaker,
and graceful degradation for non-critical nodes.

This is deliberately generic: it knows nothing about analytics. Nodes are
`name -> callable(ctx) -> NodeOutcome`. The orchestrator supplies the real node
bodies and the shared context. That separation keeps the engine unit-testable with
trivial dummy nodes (see tests/test_dag.py).

Semantics:
  * A node returns a NodeOutcome with status OK / BLOCKED / FAILED (or raises, which
    is treated as FAILED). BLOCKED means a gate refused to pass — the run halts
    cleanly with a reason (no degraded output). FAILED is an error/timeout.
  * `critical` nodes that FAIL halt the run. Non-critical nodes that FAIL are skipped
    (degraded) and the run continues; their dependents that require them are also
    skipped.
  * Circuit breaker: if the number of FAILED nodes within a single tier reaches
    `circuit_breaker`, the run halts with a diagnostic even if they were non-critical.
"""
from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class NodeStatus(str, Enum):
    OK = "OK"
    BLOCKED = "BLOCKED"     # a gate refused; halt cleanly, no degraded output
    FAILED = "FAILED"      # error or timeout
    SKIPPED = "SKIPPED"    # dependency unmet, or already-complete on resume


@dataclass
class NodeOutcome:
    status: NodeStatus = NodeStatus.OK
    reason: str = ""
    output: dict | None = None          # JSON-serialisable, persisted for resume


@dataclass
class NodeSpec:
    name: str
    deps: list[str] = field(default_factory=list)
    critical: bool = True
    timeout_s: float = 300.0
    retries: int = 1


@dataclass
class DagResult:
    status: str                          # COMPLETE | BLOCKED | FAILED
    reason: str = ""
    node_status: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, dict] = field(default_factory=dict)
    tiers: list[list[str]] = field(default_factory=list)


class DagError(Exception):
    pass


def topological_tiers(specs: list[NodeSpec]) -> list[list[str]]:
    """Kahn's algorithm producing execution tiers (each tier is independent).

    Raises DagError on an unknown dependency or a cycle.
    """
    names = {s.name for s in specs}
    for s in specs:
        for d in s.deps:
            if d not in names:
                raise DagError(f"node '{s.name}' depends on unknown node '{d}'")
    indeg = {s.name: len(s.deps) for s in specs}
    dependents: dict[str, list[str]] = {s.name: [] for s in specs}
    for s in specs:
        for d in s.deps:
            dependents[d].append(s.name)

    tiers: list[list[str]] = []
    remaining = dict(indeg)
    while remaining:
        tier = sorted(n for n, deg in remaining.items() if deg == 0)
        if not tier:
            raise DagError(f"cycle detected among: {sorted(remaining)}")
        tiers.append(tier)
        for n in tier:
            del remaining[n]
            for m in dependents[n]:
                if m in remaining:
                    remaining[m] -= 1
    return tiers


class DagEngine:
    def __init__(
        self,
        specs: list[NodeSpec],
        *,
        max_concurrency: int = 3,
        circuit_breaker: int = 3,
    ):
        self.specs = {s.name: s for s in specs}
        self.order = specs
        self.max_concurrency = max_concurrency
        self.circuit_breaker = circuit_breaker

    def run(
        self,
        node_fns: dict[str, Callable[[Any], NodeOutcome]],
        ctx: Any,
        *,
        completed: dict[str, dict] | None = None,
        on_complete: Callable[[str, NodeOutcome], None] | None = None,
    ) -> DagResult:
        """Execute the DAG.

        `completed` (name -> stored output) marks nodes already done on a resume; they
        are skipped and their outputs re-surfaced. `on_complete` is a checkpoint hook
        called after each node finishes (used to persist run state).
        """
        completed = dict(completed or {})
        tiers = topological_tiers(self.order)
        status: dict[str, NodeStatus] = {}
        outputs: dict[str, dict] = {}
        # pre-seed resumed nodes
        for name, out in completed.items():
            status[name] = NodeStatus.OK
            outputs[name] = out or {}

        for tier in tiers:
            tier_failures = 0
            to_run = [n for n in tier if n not in completed]

            # skip nodes whose deps are not OK
            runnable = []
            for n in to_run:
                if all(status.get(d) == NodeStatus.OK for d in self.specs[n].deps):
                    runnable.append(n)
                else:
                    status[n] = NodeStatus.SKIPPED
                    if on_complete:
                        on_complete(n, NodeOutcome(NodeStatus.SKIPPED,
                                                   reason="dependency not satisfied"))

            results = self._run_tier(runnable, node_fns, ctx)

            for n, outcome in results.items():
                status[n] = outcome.status
                if outcome.output is not None:
                    outputs[n] = outcome.output
                if on_complete:
                    on_complete(n, outcome)

                if outcome.status == NodeStatus.BLOCKED:
                    return DagResult("BLOCKED", outcome.reason,
                                     _s(status), outputs, tiers)
                if outcome.status == NodeStatus.FAILED:
                    tier_failures += 1
                    if self.specs[n].critical:
                        return DagResult("FAILED",
                                         f"critical node '{n}' failed: {outcome.reason}",
                                         _s(status), outputs, tiers)

            if tier_failures >= self.circuit_breaker:
                return DagResult(
                    "FAILED",
                    f"circuit breaker: {tier_failures} node(s) failed in one tier",
                    _s(status), outputs, tiers,
                )

        return DagResult("COMPLETE", "", _s(status), outputs, tiers)

    def _run_tier(self, names, node_fns, ctx) -> dict[str, NodeOutcome]:
        if not names:
            return {}
        if len(names) == 1 or self.max_concurrency <= 1:
            return {n: self._run_node(n, node_fns, ctx) for n in names}
        out: dict[str, NodeOutcome] = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(self.max_concurrency, len(names))
        ) as ex:
            futs = {ex.submit(self._run_node, n, node_fns, ctx): n for n in names}
            for fut in concurrent.futures.as_completed(futs):
                out[futs[fut]] = fut.result()
        return out

    def _run_node(self, name, node_fns, ctx) -> NodeOutcome:
        spec = self.specs[name]
        fn = node_fns.get(name)
        if fn is None:
            return NodeOutcome(NodeStatus.FAILED, f"no implementation for node '{name}'")
        attempts = spec.retries + 1
        last = ""
        for i in range(attempts):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(fn, ctx)
                    outcome = fut.result(timeout=spec.timeout_s)
                if outcome is None:
                    return NodeOutcome(NodeStatus.OK)
                # a BLOCKED gate is terminal — do not retry it
                if outcome.status in (NodeStatus.OK, NodeStatus.BLOCKED):
                    return outcome
                last = outcome.reason
            except concurrent.futures.TimeoutError:
                last = f"timeout after {spec.timeout_s}s"
            except Exception as e:  # noqa: BLE001 - engine boundary
                last = f"{type(e).__name__}: {e}"
        return NodeOutcome(NodeStatus.FAILED, last)


def _s(status: dict[str, NodeStatus]) -> dict[str, str]:
    return {k: v.value for k, v in status.items()}
