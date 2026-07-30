"""Phase 5 milestone: /analyze runs end-to-end on the local CSV and produces a
full runs/<id>/ with every artefact, all gates PASS, and provenance intact."""
from pathlib import Path

from pptx import Presentation

from atlas.lib.provenance import ProvenanceLedger
from atlas.orchestrator import run_analysis


def test_analyze_end_to_end(tmp_path):
    res = run_analysis(
        "Why did EMEA gross margin drop 4pts in Q2?",
        runs_root=tmp_path,
    )
    assert res.status == "COMPLETE", res.blocked_reason
    rd = res.run_dir

    # every promised artefact exists
    for rel in ["brief.md", "profile/emea_finance_csv.md", "hypotheses.md",
                "findings.md", "validation.md", "narrative.md", "deck.pptx",
                "speaker_notes.md", "provenance.json", "retro.md", "run.log"]:
        assert (rd / rel).exists(), f"missing {rel}"

    # queries + evidence were stored (provenance is structural)
    assert list((rd / "queries").glob("*.sql"))
    assert list((rd / "evidence").glob("*.json"))

    # all gates present and passing
    assert res.gates["GATE1_profiling"] == "PASS"
    assert res.gates["GATE2_semantics"] == "PASS"
    assert res.gates["GATE3_redteam"] == "PASS"
    assert res.gates["GATE4_provenance"] == "PASS"
    assert res.gates["GATE5_stakeholder"] == "PASS"

    # headline carries the real numbers
    assert "4.0pts" in res.headline or "4.0 pts" in res.headline.replace("pts", " pts")
    assert "mix" in res.headline

    # provenance ledger: no orphans among referenced claims; numbers match
    led = ProvenanceLedger.load(rd / "provenance.json")
    assert led.get("c_delta").value == -4.0
    assert led.get("c_gm_p1").value == 60.0
    assert led.get("c_gm_p2").value == 56.0
    assert led.get("c_mix").value == -4.0
    assert abs(led.get("c_rate").value) < 0.01

    # opportunity-sizer wired in: sized impact is provenance-stamped
    assert led.get("c_revenue_p2").value == 1000.0        # total EMEA Q2 revenue
    assert led.get("c_opportunity").value == 40.0         # 4pts mix on 1000 revenue
    assert (rd / "sizing.md").exists()
    assert (rd / "enrichment.md").exists()

    # deck skeleton now includes the opportunity slide (title + 5 content + 3 appendix = 9)
    prs = Presentation(str(rd / "deck.pptx"))
    assert len(prs.slides) == 9


def test_analyze_blocks_on_unknown_metric(tmp_path):
    """A metric with no locked definition must ESCALATE, not guess.

    'net promoter score' is deliberately absent from metrics.yaml AND shares no
    alias word with anything in it. That second property matters: `metric_from_text`
    is word-boundary anchored, so a phrase like "net revenue retention" would
    resolve to `revenue` and silently test nothing.
    """
    from atlas.semantic import MetricAmbiguity, metric_from_text, resolve_metric

    question = "Why did net promoter score drop in Q2?"

    # the semantic layer refuses outright rather than inventing a formula
    try:
        resolve_metric("net promoter score")
        raised = False
    except MetricAmbiguity:
        raised = True
    assert raised

    # ...and free-text resolution returns None rather than falling back to a default
    assert metric_from_text(question) is None

    # ...so the pipeline blocks at GATE 2 instead of quietly running a margin analysis
    res = run_analysis(question, runs_root=tmp_path)
    assert res.status == "BLOCKED"
    assert res.gates["GATE2_semantics"] == "FAIL"
    assert (res.run_dir / "BLOCKED.md").exists()
    assert "net promoter score" not in res.headline  # no headline at all on a block


def test_analyze_blocks_when_the_table_cannot_answer_the_question(tmp_path):
    """A metric can resolve cleanly and still be unanswerable *from this table*.

    Asking about churn while pointed at the EMEA finance fixture: the metric
    resolves (GATE 2 PASSES) and the descriptive playbook can in principle compute
    it, but `finance` has no churn column to bind the target role to. Atlas blocks
    and names the fix rather than analysing whatever column happens to be handy.

    This replaced an earlier capability-block assertion: `non_decomposable` used to
    have no execution path at all, which the descriptive playbook now provides.
    """
    res = run_analysis("Why did EMEA churn spike in Q2?", runs_root=tmp_path)

    assert res.status == "BLOCKED"
    # the definition resolved fine -- this is NOT a semantics failure
    assert res.gates["GATE2_semantics"] == "PASS"
    assert "cannot bind required role" in res.blocked_reason
    assert "'target'" in res.blocked_reason
    # the block must be actionable, not just a refusal
    assert "Fix:" in res.blocked_reason
    assert "does not guess" in res.blocked_reason
    assert (res.run_dir / "BLOCKED.md").exists()
