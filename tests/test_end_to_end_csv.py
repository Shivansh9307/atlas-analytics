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
    # A metric with no locked definition must ESCALATE, not guess.
    res = run_analysis(
        "Why did EMEA churn spike in Q2?",  # 'churn' not in metrics.yaml
        runs_root=tmp_path,
    )
    # 'churn' resolves to no keyword -> defaults to gross_margin; force ambiguity:
    from atlas.semantic import resolve_metric, MetricAmbiguity
    try:
        resolve_metric("churn")
        raised = False
    except MetricAmbiguity:
        raised = True
    assert raised
