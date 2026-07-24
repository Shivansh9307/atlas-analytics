"""Phase 3: the Data Quality Copilot + Readiness Gate wired into /analyze."""
from __future__ import annotations

import yaml

from atlas.config import PATHS
from atlas.lib.gates import GateStatus, gate_readiness
from atlas.orchestrator import SPECS, NODE_FNS, run_analysis


def test_quality_and_readiness_nodes_wired():
    names = {s.name for s in SPECS}
    assert {"quality", "readiness_gate"} <= names
    assert "quality" in NODE_FNS and "readiness_gate" in NODE_FNS
    explore = next(s for s in SPECS if s.name == "explore")
    assert "readiness_gate" in explore.deps          # analysis waits on the gate
    q = next(s for s in SPECS if s.name == "quality")
    assert q.deps == ["profile"]


def test_specs_match_registry_yaml():
    """orchestrator SPECS and .claude/agents/registry.yaml must stay in sync."""
    reg = yaml.safe_load((PATHS.root / ".claude" / "agents" / "registry.yaml").read_text())
    assert set(reg["nodes"]) == {s.name for s in SPECS}
    for s in SPECS:
        assert set(reg["nodes"][s.name]["deps"]) == set(s.deps), s.name


def test_emea_pipeline_still_completes(tmp_path):
    """Backward-compat: the clean fixture passes readiness and finishes."""
    r = run_analysis("Why did EMEA margin fall in Q2?", runs_root=tmp_path)
    assert r.status == "COMPLETE"
    assert r.gates["GATE_readiness"] == "PASS"
    assert "repair/readiness.md" in r.artefacts


def test_quality_node_is_noop_on_clean_source(tmp_path):
    r = run_analysis("Why did EMEA margin fall in Q2?", runs_root=tmp_path)
    state = yaml.safe_load((tmp_path / r.run_id / "pipeline_state.json").read_text())
    q = state["outputs"]["quality"]
    assert q["applied"] == [] and q["pending_approval"] == []
    assert q["score_before"] == q["score_after"] == 100.0


def test_gate_readiness_pass_and_fail():
    assert gate_readiness(True, "GO", []).status == GateStatus.PASS
    fail = gate_readiness(False, "NO-GO", ["score 40 < 60"])
    assert fail.status == GateStatus.FAIL
    assert fail.defects[0].owner == "data-quality-copilot"


def test_readiness_gate_blocks_when_not_ready(tmp_path, monkeypatch):
    """Force NO-GO by raising the score floor above the achievable maximum."""
    import atlas.quality.pipeline as pipe
    monkeypatch.setattr(pipe, "readiness_thresholds",
                        lambda: {"min_overall_score": 101, "caveats_below": 90,
                                 "max_critical_issues": 0})
    r = run_analysis("Why did EMEA margin fall in Q2?", runs_root=tmp_path)
    assert r.status == "BLOCKED"
    assert r.gates["GATE_readiness"] == "FAIL"
    assert (tmp_path / r.run_id / "BLOCKED.md").exists()
