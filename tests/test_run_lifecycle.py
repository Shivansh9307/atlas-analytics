"""Phase 1: run tracking + resume + registry/SPECS sync."""
from pathlib import Path

import yaml

from atlas.lib.run_state import RunState, list_runs
from atlas.orchestrator import SPECS, run_analysis

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / ".claude" / "agents" / "registry.yaml"
Q = "Why did EMEA gross margin drop 4pts in Q2?"


def test_registry_matches_specs():
    reg = yaml.safe_load(REGISTRY.read_text())["nodes"]
    spec_by = {s.name: s for s in SPECS}
    assert set(reg) == set(spec_by), "registry.yaml and SPECS have different node sets"
    for name, r in reg.items():
        assert sorted(r["deps"]) == sorted(spec_by[name].deps), f"{name} deps drift"
        assert r["critical"] == spec_by[name].critical, f"{name} critical drift"


def test_state_written_with_all_nodes(tmp_path):
    res = run_analysis(Q, runs_root=tmp_path)
    assert res.status == "COMPLETE"
    state = RunState.load(res.run_id, tmp_path)
    assert state.status == "COMPLETE"
    assert state.headline == res.headline
    # every node ran OK
    node_names = {s.name for s in SPECS}
    assert set(state.nodes) == node_names
    assert all(v == "OK" for v in state.nodes.values())


def test_list_runs(tmp_path):
    r1 = run_analysis(Q, runs_root=tmp_path)
    runs = list_runs(tmp_path)
    assert any(r["run_id"] == r1.run_id and r["status"] == "COMPLETE" for r in runs)


def test_resume_reruns_only_incomplete_nodes(tmp_path):
    # 1. full run
    res = run_analysis(Q, runs_root=tmp_path)
    run_dir = tmp_path / res.run_id
    assert (run_dir / "deck.pptx").exists()

    # 2. simulate interruption after 'diagnose': drop later nodes + the deck
    state = RunState.load(res.run_id, tmp_path)
    keep = {"profile", "frame", "semantics", "explore", "diagnose"}
    state.nodes = {k: v for k, v in state.nodes.items() if k in keep}
    state.outputs = {k: v for k, v in state.outputs.items() if k in keep}
    state.status = "FAILED"
    state.save(tmp_path)
    (run_dir / "deck.pptx").unlink()

    # 3. resume
    res2 = run_analysis(Q, runs_root=tmp_path, resume_run_id=res.run_id)
    assert res2.status == "COMPLETE"
    assert res2.run_id == res.run_id
    assert (run_dir / "deck.pptx").exists()            # rebuilt by resumed deck node

    # only the incomplete nodes re-ran -> their artefacts are in this session's list,
    # completed-and-skipped ones are NOT
    arts = set(res2.artefacts)
    assert "validation.md" in arts and "narrative.md" in arts   # redteam, narrative re-ran
    assert "deck.pptx" in arts
    assert "hypotheses.md" not in arts                  # explore was skipped (resumed)
    assert "brief.md" not in arts                       # semantics was skipped

    # headline reproduced correctly from rehydrated state
    assert "4.0pts" in res2.headline and "mix" in res2.headline


def test_resume_of_complete_run_is_noop(tmp_path):
    res = run_analysis(Q, runs_root=tmp_path)
    res2 = run_analysis(Q, runs_root=tmp_path, resume_run_id=res.run_id)
    assert res2.status == "COMPLETE"
    # nothing re-ran: no artefacts written this session
    assert res2.artefacts == []
