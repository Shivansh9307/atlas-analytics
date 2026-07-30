"""`SPECS` and `.claude/agents/registry.yaml` must not drift.

The constitution names these as a pair that must be edited together, and `SPECS` is
the executable truth while the YAML is the documented mirror. The pre-existing
`test_registry_matches_specs` only checked node names, deps and `critical` — which is
exactly why `timeout_s` could be declared in the YAML and silently ignored by the
code for the whole life of the project (`readiness_gate` claimed 60s and ran at the
300s default). This checks every field the YAML declares.
"""
from pathlib import Path

import pytest
import yaml

from atlas.dag import DagEngine, NodeSpec, topological_tiers
from atlas.orchestrator import NODE_FNS, SPECS

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / ".claude" / "agents" / "registry.yaml"
AGENTS = ROOT / ".claude" / "agents"


@pytest.fixture(scope="module")
def reg():
    return yaml.safe_load(REGISTRY.read_text())


def test_node_sets_match(reg):
    assert set(reg["nodes"]) == {s.name for s in SPECS}


def test_deps_and_critical_match(reg):
    by = {s.name: s for s in SPECS}
    for name, r in reg["nodes"].items():
        assert sorted(r["deps"]) == sorted(by[name].deps), f"{name}: deps drift"
        assert r["critical"] == by[name].critical, f"{name}: critical drift"


def test_timeouts_match_and_are_actually_enforced(reg):
    """The bug this test exists for: a documented timeout the engine ignores."""
    by = {s.name: s for s in SPECS}
    for name, r in reg["nodes"].items():
        declared = r.get("timeout_s")
        assert declared is not None, f"{name}: registry.yaml declares no timeout_s"
        assert by[name].timeout_s == declared, (
            f"{name}: registry.yaml says {declared}s but SPECS runs at "
            f"{by[name].timeout_s}s")


def test_every_node_names_an_agent_that_exists(reg):
    for name, r in reg["nodes"].items():
        agent = r.get("agent")
        assert agent, f"{name}: no owning agent declared"
        assert (AGENTS / f"{agent}.md").exists(), \
            f"{name}: agent '{agent}' has no .claude/agents/{agent}.md"


def test_every_node_has_an_implementation():
    assert {s.name for s in SPECS} == set(NODE_FNS)


def test_engine_block_matches_the_engine_defaults(reg):
    """registry.yaml documents engine settings that nothing loads; if the code's
    defaults move, the doc must move with them."""
    e = reg["engine"]
    probe = DagEngine([NodeSpec("x")])
    assert e["max_concurrency"] == probe.max_concurrency
    assert e["circuit_breaker"] == probe.circuit_breaker
    assert e["default_timeout_s"] == NodeSpec("x").timeout_s
    assert e["retries"] == NodeSpec("x").retries


def test_documented_tiers_match_the_computed_ones(reg):
    """The tier comment is informational, but a stale one is worse than none."""
    tiers = topological_tiers(SPECS)
    text = REGISTRY.read_text()
    for i, tier in enumerate(tiers):
        line = next((ln for ln in text.splitlines()
                     if ln.strip().startswith(f"#   tier {i}:")), None)
        assert line, f"tier {i} is not documented in registry.yaml"
        for node in tier:
            assert node in line, f"tier {i} comment omits '{node}': {line.strip()}"
    assert f"#   tier {len(tiers)}:" not in text, "registry.yaml documents extra tiers"


def test_graph_is_acyclic_and_ordered():
    tiers = topological_tiers(SPECS)
    seen: set[str] = set()
    by = {s.name: s for s in SPECS}
    for tier in tiers:
        for n in tier:
            assert all(d in seen for d in by[n].deps), f"{n} runs before its deps"
        seen |= set(tier)
    assert seen == {s.name for s in SPECS}
