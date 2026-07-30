"""Question routing recorded in the run, and defect ownership surfaced on a block.

Both were data structures the codebase carried but never used: `router.classify()`
ran only in advisory slash commands, and `gates.ROUTING` existed with no production
caller, so a failed gate never told anyone who should fix it.
"""
from pathlib import Path

import pytest

from atlas.lib.gates import Defect, GateResult, GateStatus, ROUTING, routing_note
from atlas.lib.run_state import RunState
from atlas.orchestrator import run_analysis

MARGIN_Q = "Why did EMEA gross margin drop 4pts in Q2?"


# --------------------------- routing ---------------------------
def test_routing_is_recorded_in_the_run_state(tmp_path):
    res = run_analysis(MARGIN_Q, runs_root=tmp_path)
    st = RunState.load(res.run_id, tmp_path)
    r = st.outputs["frame"]["routing"]
    assert r["level"] == 3                      # "why" -> root-cause
    assert r["label"] == "root-cause"
    assert r["command"] == "/analyze"
    assert r["confidence"] == "high"
    assert r["reason"]


def test_routing_survives_a_classifier_failure(monkeypatch, tmp_path):
    """Routing is advisory; it must never be able to fail a run."""
    import atlas.lib.router as router_mod

    def boom(_q):
        raise RuntimeError("classifier exploded")

    monkeypatch.setattr(router_mod, "classify", boom)
    res = run_analysis(MARGIN_Q, runs_root=tmp_path)
    assert res.status == "COMPLETE"
    st = RunState.load(res.run_id, tmp_path)
    assert st.outputs["frame"]["routing"] == {}


# --------------------------- defect ownership ---------------------------
def test_column_binding_defects_have_an_owner():
    assert ROUTING["column_binding"] == ("semantic-architect", 1)


def test_routing_note_names_the_owning_agent_and_cap():
    g = GateResult("GATE3_redteam", GateStatus.FAIL,
                   [Defect("failed_rederivation", "numbers disagree")])
    note = routing_note(g)
    assert "failed_rederivation" in note
    assert "sql-engineer" in note
    assert "rework cap 2" in note


def test_routing_note_is_empty_for_a_passing_gate():
    assert routing_note(GateResult("G", GateStatus.PASS)) == ""


def test_routing_note_deduplicates_repeated_defect_kinds():
    g = GateResult("GATE4_provenance", GateStatus.FAIL, [
        Defect("unprovenanced_number", "c1"),
        Defect("unprovenanced_number", "c2"),
        Defect("unprovenanced_number", "c3"),
    ])
    assert routing_note(g).count("unprovenanced_number") == 1


def test_blocked_md_tells_you_who_owns_the_fix(tmp_path):
    res = run_analysis("Why did net promoter score drop in Q2?", runs_root=tmp_path)
    assert res.status == "BLOCKED"
    text = (res.run_dir / "BLOCKED.md").read_text()
    assert "## Who owns this" in text
    assert "metric_ambiguity" in text
    assert "semantic-architect" in text


def test_unknown_defect_kind_falls_back_to_the_orchestrator():
    d = Defect("something_new", "detail")
    assert d.owner == "orchestrator"
    assert d.cap == 0


# --------------------------- the deliberate non-change ---------------------------
def test_a_blocked_gate_is_still_terminal():
    """No automatic rework loop was added, and that is deliberate.

    In the deterministic engine a gate evaluates already-computed stored values, so
    re-running it yields a bit-identical failure. A retry loop would spend budget to
    reach the same answer and make a hard, honest block look intermittent. The
    ownership note replaces it: it says who should act, without pretending the
    machine can fix itself.
    """
    from atlas.dag import NodeStatus
    assert NodeStatus.BLOCKED.value == "BLOCKED"
    # gate evaluators are pure: same inputs, same verdict
    from atlas.lib.gates import gate3_redteam
    a = gate3_redteam(False, ["attack"])
    b = gate3_redteam(False, ["attack"])
    assert a.status == b.status and len(a.defects) == len(b.defects)


def test_readiness_gate_still_blocks_hard():
    """Explicitly pinned: the readiness gate must not be softened by any rework work."""
    from atlas.lib.gates import gate_readiness
    g = gate_readiness(False, "NO-GO", ["quality too low"])
    assert not g.passed
    assert g.status == GateStatus.FAIL
    assert g.defects[0].kind == "data_not_ready"
